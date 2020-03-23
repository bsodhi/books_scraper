"""
Written with a lot of help from StackOverflow community 
and Python API documentation. Greatly appreciated!
"""
import os
import sys
import glob
import csv
import re
import lxml
import time
import requests
import random
import traceback
import urllib3
import urllib.parse
import scholarly
from pathlib import Path
from bs4 import BeautifulSoup
from datetime import datetime as DT
from fake_useragent import UserAgent
from getpass import getpass


# Disable the SSL warnings
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

UA = UserAgent()
FIXED_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.14; rv:74.0) Gecko/20100101 Firefox/74.0"
DEBUG = False
HTTP_TIMEOUT_SEC = 5
HTTP_DELAY_SEC = 2
ROW_KEYS = ['author', 'title', 'language', 'genre', 'avg_rating',
            'ratings', 'reviews', 'book_format', 'pages', 
            'isbn', 'pub_year', 'url', 'synopsis']
GS_ROW_KEYS = ["author", "title", "citedby", "url", "abstract"]


class Obj:
    """A wrapper for some value which can be passed around by reference.
    """
    val = 0


def log(msg):
    ts = DT.now().strftime("%Y-%m-%d@%I:%M:%S%p")
    print("[{0}] : {1}".format(ts, msg))


def debug(msg):
    if DEBUG:
        log(msg)


def make_http_request(url):
    log("Requesting URL {0}. Delay {1}s".format(url, HTTP_DELAY_SEC))
    time.sleep(HTTP_DELAY_SEC)
    return requests.get(url,
                        headers={'User-Agent': UA.random},
                        timeout=HTTP_TIMEOUT_SEC)


def make_page_soup(page_url):
    page = make_http_request(page_url)
    if page.status_code == requests.codes.ok:
        return BeautifulSoup(page.content, 'lxml')
    else:
        log("Failed to get page at URL {0}. Error: {1}".format(
            page_url, page.reason))


def _get_pub_date(dt_str):
    pub_dt = '--'
    try:
        s = dt_str.strip()
        pub_dt = s[s.find("Published")+9:s.find("by")].strip()
    except AttributeError:
        log("\t**** Could not find publish date.")
    return pub_dt


def _try_get_item(soup, sel):
    val = "--"
    try:
        val = soup.select(sel)[0].text.strip()
    except Exception:
        log("**** Failed to get value for "+sel)
    return val


def get_book_detail(url):
    book_info = {"book_format": "--", "pages": "--", "synopsis": "--",
                 "isbn": "--", "language": "--", "pub_year": "--",
                 "url": url, "avg_rating": "--", "ratings": "--",
                 "reviews": "--", "author": "--", "title": "--"}
    soup = make_page_soup("https://www.goodreads.com"+url)

    if not soup:
        return book_info

    book_info["avg_rating"] = _try_get_item(
        soup, "#bookMeta > span:nth-child(2)")
    book_info["ratings"] = _try_get_item(soup, "a.gr-hyperlink:nth-child(7)")
    book_info["reviews"] = _try_get_item(soup, "a.gr-hyperlink:nth-child(9)")
    book_info["author"] = _try_get_item(
        soup, "#bookAuthors > span:nth-child(2)")
    book_info["title"] = _try_get_item(soup, "#bookTitle")

    dn = soup.find("div", {"id": "details", "class": "uitext darkGreyText"})
    if dn:
        # dn = soup.find("div#details.uitext.darkGreyText")
        temp = dn.find("span", {"itemprop": "bookFormat"})
        book_info["book_format"] = temp.text.strip() if temp else "--"
        temp = dn.find("span", {"itemprop": "numberOfPages"})
        book_info["pages"] = temp.text.strip() if temp else "--"

        isbns = dn.select("div.clearFloats:nth-child(2) > div:nth-child(1)")
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
        book_info["pub_year"] = _get_pub_date(
            pub_yr[0].text) if pub_yr else "--"

        book_info["synopsis"] = _try_get_item(
            soup, "div#description.readable.stacked")
        book_info["url"] = url
        return book_info
    else:
        return book_info


def main(in_file, out_file):
    try:
        bc = Obj()
        with open(in_file) as incsv:
            reader = csv.DictReader(incsv)
            with open(out_file, "w", newline='') as outcsv:
                dw = csv.DictWriter(outcsv, ROW_KEYS, extrasaction='ignore')
                dw.writeheader()
                for row in reader:
                    try:
                        qry = urllib.parse.quote(row['title'])
                        url = "https://www.goodreads.com/search?q={0}".format(
                            qry)
                        soup = make_page_soup(url)
                        book_url = soup.find(
                            "a", {"class": "bookTitle"})["href"]
                        if book_url:
                            book = get_book_detail(book_url.split("?")[0])
                            book["genre"] = row['genre']
                            dw.writerow(book)
                            bc.val += 1
                            print("Processed {0} books.".format(bc.val))
                        else:
                            log("*** Book URL not found!")
                    except Exception as ex:
                        log("**** Error "+str(ex)+". Continuing to next.")
                        time.sleep(15)

    except Exception as ex:
        log("Exiting. Error occurred. "+str(ex))


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: {0} INPUT_FILE_PATH OUTPUT_FILE_PATH".format(
            sys.argv[0]))
    else:
        main(sys.argv[1], sys.argv[2])
