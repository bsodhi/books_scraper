"""
Written with a lot of help from StackOverflow community
and Python API documentation. Greatly appreciated!
"""
import os
import glob
import math
import csv
import re
import lxml
import time
import requests
import random
import traceback
import argparse
import urllib3
from pathlib import Path
from bs4 import BeautifulSoup
from datetime import datetime as DT
from selenium import webdriver
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By
from getpass import getpass
from selenium.webdriver.common.keys import Keys
from zipfile import ZipFile

# Disable the SSL warnings
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

DEBUG = False
GS_ROW_KEYS = ["author", "title", "publication", "citedby", "url", "abstract"]


class Obj:
    """A wrapper for some value which can be passed around by reference.
    """
    val = 0


def log(msg):
    ts = DT.now().strftime("%Y-%m-%d@%I:%M:%S%p")
    print("[{0}] : {1}".format(ts, msg), flush=True)


def debug(msg):
    if DEBUG:
        log(msg)


def try_get_item(soup, sel):
    val = "--"
    try:
        val = soup.select(sel)[0].text.strip()
    except Exception:
        debug("**** Failed to get value for "+sel)
    return val


class GSScraper(object):
    def __init__(self, query, web_browser="firefox", max_recs=10,
                 out_dir="output", timeout=10,
                 scholar_id=None, scholar_password=None):
        self.timeout = timeout
        self.web_browser = web_browser
        self.max_recs = int(max_recs)
        self.query = query
        self.scholar_id = scholar_id
        self.scholar_password = scholar_password
        self.out_dir = out_dir
        Path(self.out_dir).mkdir(parents=True, exist_ok=True)

    def _init_selinium(self):
        log("Initializing webdriver for "+self.web_browser)
        if "chrome" == self.web_browser:
            self.browser = webdriver.Chrome()
        elif "firefox" == self.web_browser:
            from selenium.webdriver.firefox.options import Options
            opt = Options()
            opt.headless = True
            self.browser = webdriver.Firefox(options=opt)
        elif "safari" == self.web_browser:
            self.browser = webdriver.Safari()
        elif "edge" == self.web_browser:
            self.browser = webdriver.Edge()
        else:
            raise Exception("Unsupported browser: "+self.web_browser)

        self.web_wait = WebDriverWait(self.browser, self.timeout)

    def _web_wait(self, by, val):
        self.web_wait.until(
            EC.presence_of_element_located((by, val)))
        wtime = random.randrange(3, 10)
        log("Waiting for {0}s".format(wtime))
        time.sleep(wtime)

    def _extract_gs_data(self, html):
        soup = BeautifulSoup(html, "lxml")
        items = soup.select("#gs_res_ccl_mid > div.gs_r.gs_or.gs_scl")

        data = []
        for obj in items:
            title = try_get_item(obj, "h3")
            temp = try_get_item(obj, "div.gs_ri > div.gs_a")
            authors = temp[:temp.index("-")] if "-" in temp else temp
            pub = temp[temp.index("-")+1:] if "-" in temp else "--"
            abst = try_get_item(obj, "div.gs_ri > div.gs_rs")
            cited_by = try_get_item(obj,
                                    "div.gs_ri > div.gs_fl > a:nth-child(3)").replace("Cited by ", "")
            url = obj.select_one("div.gs_ggs.gs_fl > div > div > a")
            url = url["href"] if url else "--"
            data.append({"title": title, "author": authors, "publication": pub,
                         "citedby": cited_by, "url": url, "abstract": abst})
        return data

    def _google_scholar_pager(self, query_str):
        log("Starting results paginator...")
        self._init_selinium()
        # Login to google if credentials provided
        try:
            if self.scholar_id and self.scholar_password:
                log("Logging in to Google Scholar.")
                self.browser.get(
                    "https://accounts.google.com/Login?hl=en&continue=https://scholar.google.com/")
                self._web_wait(By.ID, 'identifierId')
                user_id = self.browser.find_element_by_id(
                    "identifierId")
                user_id.clear()
                user_id.send_keys(self.scholar_id)
                user_id.send_keys(Keys.RETURN)
                log("Sent the user ID to server.")
                self._web_wait(By.NAME, 'password')
                passw = self.browser.find_element_by_name(
                    "password")
                log("Found password input box.")
                passw.send_keys(self.scholar_password)
                time.sleep(4)
                self.browser.find_element_by_id("passwordNext").click()
                log("Sent the credentials to server.")
            else:
                log("Using Google Scholar without logging in.")
        except Exception as ex:
            traceback.print_exc()
            log("Will attempt using Google Scholar without logging in.")

        pg_url = "https://scholar.google.com"
        self.browser.get(pg_url)
        self._web_wait(By.ID, 'gs_hdr_tsi')
        log("Loaded Google Scholar page.")
        query = self.browser.find_element_by_id("gs_hdr_tsi")
        query.clear()
        query.send_keys(query_str)
        query.send_keys(Keys.RETURN)
        # self.browser.find_element_by_id("gs_hdr_tsb").click()
        log("Sent search query to website.")
        self._web_wait(By.CLASS_NAME, 'gs_ab_mdw')
        has_next = True
        page_count = 0
        while has_next:
            # Throttle the crawling regularly at random interval
            if page_count >= random.randrange(5, 10):
                ptt = random.randrange(6, 16)
                time.sleep(ptt)
                log("Throttling down the paginator by {0}s".format(ptt))
                page_count = 0
            else:
                time.sleep(random.randrange(3, 7))
            yield self.browser.page_source
            page_count += 1
            try:
                nb = self.browser.find_element_by_link_text("Next")
                if nb:
                    log("Going to next page...")
                    nb.click()
                    self._web_wait(
                        By.CLASS_NAME, 'gs_ico_nav_next')
                else:
                    has_next = False
            except Exception as ex:
                traceback.print_exc()
                log("Error when paginating to next. "+str(ex))

    def screape_google_scholar_paged(self):
        try:
            for q in self.query.split(","):
                csv_path = self.out_dir + "/" + q.strip().replace(" ", "_")+"_gs.csv"
                with open(csv_path, "w", newline='') as csvfile:
                    dw = csv.DictWriter(csvfile, GS_ROW_KEYS,
                                        extrasaction='ignore')
                    dw.writeheader()
                    csvfile.flush()
                    pager = self._google_scholar_pager(q)
                    recs = 0
                    while recs < self.max_recs:
                        try:
                            gsr_html = next(pager)
                            log("Fetched {0}/{1} results.".format(recs, self.max_recs))
                            if not gsr_html:
                                break
                            data = self._extract_gs_data(gsr_html)
                            dw.writerows(data)
                            csvfile.flush()
                            recs += len(data)
                        except Exception as ex:
                            traceback.print_exc()
                            log("Error when extracting information from page. "+str(ex))

        except Exception as ex:
            traceback.print_exc()
        finally:
            self.browser.close()
