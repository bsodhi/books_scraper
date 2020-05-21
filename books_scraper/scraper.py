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
import urllib3
from pathlib import Path
from bs4 import BeautifulSoup
from datetime import datetime as DT
from fake_useragent import UserAgent
from selenium import webdriver
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By
from getpass import getpass
from selenium.webdriver.common.keys import Keys
from zipfile import ZipFile

# Disable the SSL warnings
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

UA = UserAgent()
FIXED_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.14; rv:74.0) Gecko/20100101 Firefox/74.0"
DEBUG = False
LOG_FILE = None
HTTP_TIMEOUT_SEC = 5
HTTP_DELAY_SEC = 2
ROW_KEYS = ['author', 'title', 'language', 'genre', 'avg_rating',
            'ratings', 'reviews', 'book_format', 'pages',
            'isbn', 'pub_year', 'publisher', 'url', 'synopsis']
GS_ROW_KEYS = ["author", "title", "publication", "citedby", "url", "abstract"]
NDL_ROW_KEYS = ["author", "title", "language", "url", "abstract"]


class Obj:
    """A wrapper for some value which can be passed around by reference.
    """
    val = 0


def log(msg):
    ts = DT.now().strftime("%Y-%m-%d@%I:%M:%S%p")
    msg_str = "[{0}] : {1}".format(ts, msg)
    if not LOG_FILE:
        print(msg_str, flush=True)
    else:
        with open(LOG_FILE, "a") as fp:
            print(msg_str, file=fp, flush=True)


def debug(msg):
    if DEBUG:
        log(msg)


def overwrite_existing_path(path_str, options=None):
    fo = "yes"
    if os.path.exists(path_str):
        fo = input(
            "Path {0} already exists. Would you like to overwrite it? {1}: ".format(path_str, options if options else "[yes/no]"))

    return fo


def make_http_request(url, timeout=10, http_delay_sec=4):
    log("Requesting URL {0}. Delay {1}s".format(url, http_delay_sec))
    time.sleep(http_delay_sec)
    return requests.get(url,
                        headers={'User-Agent': UA.random},
                        timeout=timeout)


def try_get_item(soup, sel):
    val = "--"
    try:
        val = soup.select(sel)[0].text.strip()
    except Exception:
        debug("**** Failed to get value for "+sel)
    return val


class BookScraper(object):
    def __init__(self, query, web_browser="firefox", max_recs=10, html_dir=None,
                 use_cached_books=True, gr_login=None,
                 gr_password=None, out_dir="output", timeout=10, http_delay_sec=2):
        self.timeout = timeout
        self.http_delay_sec = http_delay_sec
        self.web_browser = web_browser
        self.max_recs = int(max_recs)
        self.query = query
        self.html_dir = html_dir
        ucb = str(use_cached_books).lower().strip()
        tv = ["true", "t", "1", "yes", "on", "y"]
        self.use_cached_books = ucb in tv
        Path(self.html_dir).mkdir(parents=True, exist_ok=True)
        self.gr_login = gr_login
        self.gr_password = gr_password
        self.out_dir = out_dir
        Path(self.out_dir).mkdir(parents=True, exist_ok=True)
        log("Using cached books: "+str(self.use_cached_books) +
            ". Timeout = "+str(self.timeout))

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

    def _crawl_goodreads_shelves(self):
        crawled_files = {}
        self._init_selinium()
        login_url = "https://www.goodreads.com/user/sign_in"
        self.browser.get(login_url)
        log("Loaded login page.")
        username = self.browser.find_element_by_id("user_email")
        password = self.browser.find_element_by_id("user_password")
        username.send_keys(self.gr_login)
        password.send_keys(self.gr_password)
        self.browser.find_element_by_name("sign_in").submit()
        log("Sent login request to website.")
        try:
            self._web_wait(By.CLASS_NAME, 'siteHeader__personal')
            log("Loaded the user home page.")
        except Exception:
            log("Failed to login.")
            raise

        if "Recent updates" in self.browser.title:
            shelf_url = "https://www.goodreads.com/shelf/show/{0}?page={1}"
            for gn in self.query.split(","):
                gn = gn.strip()
                crawled_files[gn] = []
                no_of_shelves = math.ceil(int(self.max_recs)/50) + 1
                for p in range(1, no_of_shelves):
                    html_file = "shelf_{0}_p{1}.html".format(gn, p)
                    crawled_files[gn].append(html_file)
                    url = shelf_url.format(gn, p)
                    if self.use_cached_books and self._is_cached(html_file):
                        log("Page {0} already downloaded. Skipping to next.".format(
                            url))
                        continue

                    time.sleep(2)
                    log("Fetching ["+url+"]")
                    self.browser.get(url)
                    html_source = self.browser.page_source
                    self._cache_page(html_file, html_source)

            log("Closing the browser")
            self.browser.close()
        else:
            raise Exception("Failed to load the landing page.")
        return crawled_files

    def _is_cached(self, file_name):
        file_path = "{0}/{1}".format(self.html_dir, file_name)
        return os.path.exists(file_path)

    def _cache_page(self, file_name, page_content):
        file_path = "{0}/{1}".format(self.html_dir, file_name)
        with open(file_path, "w") as html:
            html.write(page_content)
            log("Saved HTML at: "+file_path)

    def _get_cache_page(self, file_name):
        file_path = "{0}/{1}".format(self.html_dir, file_name)
        with open(file_path, "r") as html:
            return html.read()

    def _get_pub_date(self, dt_str):
        pub_dt = '--'
        pub = '--'
        try:
            s = dt_str.strip()
            bi = s.find(" by ")
            if s.startswith("Published") and bi > 0:
                pub_dt = s[9:bi].strip()
                pub = s[bi+4:].strip()

        except AttributeError:
            log("\t**** Could not find publish date.")
        return pub_dt, pub

    def _get_book_detail(self, url):
        book_info = dict(zip(ROW_KEYS, ["" for _ in ROW_KEYS]))

        # https://www.goodreads.com/book/show/6708.The_Power_of_Now
        soup = None

        file_name = "".join(url.split("/"))+".html"
        if self.use_cached_books and self._is_cached(file_name):
            log("Using cached file "+file_name)
            html = self._get_cache_page(file_name)
            soup = BeautifulSoup(html, "lxml")
        else:
            page_url = "https://www.goodreads.com"+url
            page = make_http_request(page_url, timeout=self.timeout,
                                     http_delay_sec=self.http_delay_sec)
            if page.status_code == requests.codes.ok:
                self._cache_page(file_name, str(page.content, encoding="utf8"))
                soup = BeautifulSoup(page.content, 'lxml')
            else:
                log("Failed to get page at URL {0}. Error: {1}".format(
                    page_url, page.reason))

        if not soup:
            return book_info

        book_info["avg_rating"] = try_get_item(
            soup, "#bookMeta > span:nth-child(2)")
        book_info["ratings"] = try_get_item(
            soup, "a.gr-hyperlink:nth-child(7)")
        book_info["reviews"] = try_get_item(
            soup, "a.gr-hyperlink:nth-child(9)")
        book_info["author"] = try_get_item(
            soup, "#bookAuthors > span:nth-child(2)")
        book_info["title"] = try_get_item(soup, "#bookTitle")

        dn = soup.find(
            "div", {"id": "details", "class": "uitext darkGreyText"})
        if dn:
            # dn = soup.find("div#details.uitext.darkGreyText")
            temp = dn.find("span", {"itemprop": "bookFormat"})
            book_info["book_format"] = temp.text.strip() if temp else "--"
            temp = dn.find("span", {"itemprop": "numberOfPages"})
            book_info["pages"] = temp.text.strip() if temp else "--"

            isbns = dn.select(
                "div.clearFloats:nth-child(2) > div:nth-child(1)")
            isbn = "--"
            try:
                if isbns and isbns[0].text == "ISBN":
                    isbn = dn.select(
                        "div.clearFloats:nth-child(2) > div:nth-child(2)")[0].text
            except AttributeError:
                log("\t**** Could not find ISBN.")
            book_info["isbn"] = isbn.strip()

            temp = dn.find("div", {"itemprop": "inLanguage"})
            book_info["language"] = temp.text.strip() if temp else "--"

            pub_yr = soup.select("div.row:nth-child(2)")

            pub_dt, pub = self._get_pub_date(
                pub_yr[0].text) if pub_yr else ("--", "--")
            book_info["pub_year"] = pub_dt
            book_info["publisher"] = pub

            book_info["synopsis"] = try_get_item(
                soup, "div#description.readable.stacked > span:nth-child(2)")
            book_info["url"] = url
            return book_info
        else:
            return book_info

    def _extract_books_from_shelf(self, genre, writer, soup, books_count):

        # Selector for book entries on a shelf page
        book_entry_sel = ".mainContent .leftContainer .elementList"
        for n in soup.select(book_entry_sel):
            try:
                book = {}
                book["genre"] = genre
                book_url = n.find("a", {"class": "bookTitle"})["href"]
                book.update(self._get_book_detail(book_url))
                writer.writerow(book)
                if books_count.val >= self.max_recs:
                    break
                books_count.val += 1
                log("Processed {0}/{1} books in {2}.".format(
                    books_count.val, self.max_recs, genre))
            except Exception as ex:
                msg = str(ex)
                log("Error in getting book info: "+msg+". Continuing.")
                if DEBUG:
                    traceback.print_exc()
                if "ConnectionResetError" in msg:
                    log("Waiting for 15s before attempting next request.")
                    time.sleep(15)

    def scrape_goodreads_books(self):
        try:
            crawled_files = self._crawl_goodreads_shelves()
            for genre in crawled_files:
                fn = genre+"_GOODREADS.csv"
                out_file = "{0}/{1}".format(self.out_dir, fn)

                with open(out_file, "w", newline='') as csvfile:
                    dw = csv.DictWriter(csvfile, ROW_KEYS,
                                        extrasaction='ignore')
                    dw.writeheader()
                    csvfile.flush()
                    shelf_pages = []
                    for file_name in crawled_files[genre]:
                        # File name is like: "shelf_{0}_p{1}.html"
                        shelf_pages.extend(
                            glob.glob("{0}/{1}".format(self.html_dir, file_name)))
                    bc = Obj()
                    for h in shelf_pages:
                        log("Extracting data from {0}".format(h))
                        # "/parent/path/shelf_{1}_p{2}.html"
                        gnr = h.split("/")[-1].split("_")[1]
                        with open(h, 'r') as fp:
                            soup = BeautifulSoup(fp, 'lxml')

                        self._extract_books_from_shelf(
                            gnr, dw, soup, books_count=bc)
                        csvfile.flush()
            log("Scraping complete.")
        except Exception as ex:
            log("Error occurred when crawing: "+str(ex))
            traceback.print_exc()
        except KeyboardInterrupt:
            log("Exiting on user request (pressed Ctrl+C)")

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

    def _get_amazon_book_info(self, html):
        book_info = dict(zip(ROW_KEYS, ["" for _ in ROW_KEYS]))
        try:
            soup = BeautifulSoup(html, "lxml")
            # Extract book info
            book_info["genre"] = try_get_item(
                soup, "ul.a-size-small > li:nth-last-child(1)")
            book_info["synopsis"] = try_get_item(soup, 
                "#bookDescription_feature_div").replace("\n", "")
            book_info["title"] = try_get_item(soup, "#title > span")
            al = soup.select("span.author")
            authors = []
            for a in al:
                authors.append(a.text.strip())
            book_info["author"] = ", ".join(authors).replace("\n", "")
            book_info["avg_rating"] = try_get_item(soup, "span.reviewCountTextLinkedHistogram")
            book_info["ratings"] = try_get_item(soup, "#acrCustomerReviewText")
            book_info["book_format"] = try_get_item(soup, "#productSubtitle")
            
            ul = soup.select(
                "td.bucket > div:nth-child(2) > ul:nth-child(1) > li")
            for li in ul:
                txt = li.text.strip()
                # print(">>> TEXT={}".format(txt))
                if txt.startswith("Print Length:"):
                    book_info["pages"] = txt.split(":")[1].strip()
                elif txt.startswith("Publisher:"):
                    book_info["publisher"] = txt.split(":")[1].strip()
                elif txt.startswith("Publication Date:"):
                    book_info["pub_year"] = txt.split(":")[1].strip()
                elif txt.startswith("Language:"):
                    book_info["language"] = txt.split(":")[1].strip()
                elif txt.startswith("Format:"):
                    book_info["book_format"] = txt.split(":")[1].strip()

        except Exception as ex:
            log("Error occurred when fetching Amazon book info: {}".format(ex))
        log("Book info: {}".format(book_info))
        return [book_info]

    def _extract_amazon_data(self, html):
        soup = BeautifulSoup(html, "lxml")
        items = soup.select(
            "div.s-main-slot.s-result-list > div.s-result-item")
        print("Records count: {}".format(len(items)))
        data = []
        sel_title = "div:nth-child(1) > span:nth-child(1) > div:nth-child(1) > div:nth-child(1) > div:nth-child(2) > div:nth-child(2) > div:nth-child(1) > div:nth-child(1) > div:nth-child(1) > div:nth-child(1) > div:nth-child(1) > h2:nth-child(1) > a:nth-child(1) > span:nth-child(1)"

        sel_auth = "div:nth-child(1) > span:nth-child(1) > div:nth-child(1) > div:nth-child(1) > div:nth-child(2) > div:nth-child(2) > div:nth-child(1) > div:nth-child(1) > div:nth-child(1) > div:nth-child(1) > div:nth-child(1) > div:nth-child(2) > a:nth-child(2)"

        sel_url = "div:nth-child(1) > span:nth-child(1) > div:nth-child(1) > div:nth-child(1) > div:nth-child(2) > div:nth-child(2) > div:nth-child(1) > div:nth-child(1) > div:nth-child(1) > div:nth-child(1) > div:nth-child(1) > h2:nth-child(1) > a:nth-child(1)"

        sel_book_type = "div:nth-child(1) > span:nth-child(1) > div:nth-child(1) > div:nth-child(1) > div:nth-child(2) > div:nth-child(2) > div:nth-child(1) > div:nth-child(2) > div:nth-child(1) > div:nth-child(1)"

        sel_rating = "div:nth-child(1) > span:nth-child(1) > div:nth-child(1) > div:nth-child(1) > div:nth-child(2) > div:nth-child(2) > div:nth-child(1) > div:nth-child(1) > div:nth-child(1) > div:nth-child(1) > div:nth-child(2) > div:nth-child(1) > span:nth-child(1)"

        sel_count_rating = "div:nth-child(1) > span:nth-child(1) > div:nth-child(1) > div:nth-child(1) > div:nth-child(2) > div:nth-child(2) > div:nth-child(1) > div:nth-child(1) > div:nth-child(1) > div:nth-child(1) > div:nth-child(2) > div:nth-child(1) > span:nth-child(2)"

        for obj in items:
            book_info = dict(zip(ROW_KEYS, ["" for _ in ROW_KEYS]))
            try:
                url_obj = obj.select_one(sel_url)
                book_info["url"] = url_obj["href"] if url_obj else "--"
                book_info["title"] = try_get_item(obj, sel_title)
                book_info["author"] = try_get_item(obj, sel_auth)

                rt_obj = obj.select_one(sel_rating)
                book_info["avg_rating"] = rt_obj["aria-label"] if rt_obj else "--"
                rtc_obj = obj.select_one(sel_count_rating)
                book_info["ratings"] = rtc_obj["aria-label"] if rtc_obj else "--"

                book_info["book_format"] = try_get_item(obj, sel_book_type)

                data.append(book_info)
            except Exception as ex:
                traceback.print_exc()
                log("Error when extracting information from Amazon page. "+str(ex))
        return data

    def _extract_ndl_data(self, html):
        soup = BeautifulSoup(html, "lxml")
        items = soup.select("#browse-result-group > div.list-group-item")
        print("Records count: {}".format(len(items)))
        data = []
        for obj in items:
            try:
                title_obj = obj.select_one("div.col-md-11.col-sm-12 > h4 > a")
                url = title_obj["href"] if title_obj else "--"
                title = title_obj.text.strip()
                authors = try_get_item(obj, "div.doc-author.overflow-off")
                abst = try_get_item(obj, "div.col-sm-7.hidden-xs > font")
                lang_obj = obj.select_one(
                    "div > div.col-sm-5 > div.icons > span")
                lang = lang_obj["title"] if lang_obj else "--"

                data.append({"title": title, "author": authors, "language": lang,
                             "url": url, "abstract": abst})
            except Exception as ex:
                traceback.print_exc()
                log("Error when extracting information from NDL page. "+str(ex))
        return data

    def extract_from_zip(self, zip_file, src_type):
        csv_path = os.path.join(self.out_dir, "local_cs.csv")
        with open(csv_path, "w", newline='') as csvfile:
            hdr_keys = []
            if src_type == "AZ" or src_type == "AZB" :
                hdr_keys = ROW_KEYS
            elif src_type == "GS":
                hdr_keys = GS_ROW_KEYS
            else:
                hdr_keys = NDL_ROW_KEYS
            dw = csv.DictWriter(csvfile, hdr_keys, extrasaction='ignore')
            dw.writeheader()
            csvfile.flush()
            with ZipFile(zip_file) as myzip:
                recs = 0
                zitems = [x for x in myzip.namelist()
                          if x.endswith(".html")
                          and "__MACOSX" not in x
                          and "DS_Store" not in x]
                log("ZIP file {0} contains {1} items.".format(
                    zip_file, len(zitems)))
                for zz in zitems:
                    try:
                        log("Extracting HTML from ZIP entry: "+str(zz))
                        with myzip.open(zz) as zf:
                            html = zf.read()
                            log("Length of ZIP entry HTML: "+str(len(html)))
                            if src_type == "NDL":
                                data = self._extract_ndl_data(html)
                            elif src_type == "GS":
                                data = self._extract_gs_data(html)
                            elif src_type == "AZ":
                                data = self._extract_amazon_data(html)
                            elif src_type == "AZB":
                                data = self._get_amazon_book_info(html)
                            else:
                                raise Exception(
                                    "Unsupported HTML source: "+str(src_type))
                            dw.writerows(data)
                            csvfile.flush()
                            recs += 1
                            log("Processed {0}/{1} files.".format(recs,
                                                                  len(zitems)))
                    except Exception as ex:
                        traceback.print_exc()
                        log("Error when extracting information from page. "+str(ex))
