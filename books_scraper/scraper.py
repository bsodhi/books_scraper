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
from fake_useragent import UserAgent
from selenium import webdriver
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By
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


def overwrite_existing_path(path_str, options=None):
    fo = "yes"
    if os.path.exists(path_str):
        fo = input(
            "Path {0} already exists. Would you like to overwrite it? {1}: ".format(path_str, options if options else "[yes/no]"))

    return fo


def make_http_request(url):
    log("Requesting URL {0}. Delay {1}s".format(url, HTTP_DELAY_SEC))
    time.sleep(HTTP_DELAY_SEC)
    return requests.get(url,
                        headers={'User-Agent': UA.random},
                        timeout=HTTP_TIMEOUT_SEC)


class BookScraper(object):
    def __init__(self, web_browser, max_recs, query, html_dir=None,
                 use_cached_books=True, gr_login=None,
                 gr_password=None, out_dir="output"):
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
        log("Using cached books: "+str(self.use_cached_books))

    def _init_selinium(self):
        if not self.gr_login:
            self.gr_login = input("Goodreads login ID (an email address): ")
            self.gr_password = getpass(prompt="Password: ")
        log("Starting webdriver...")
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

    def _crawl_goodreads_shelves(self):
        crawled_files = []
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
        timeout = 5  # seconds
        try:
            WebDriverWait(self.browser, timeout).until(
                EC.presence_of_element_located((By.CLASS_NAME, 'siteHeader__personal')))
            log("Loaded the user home page.")
        except Exception:
            log("Failed to login.")
            raise

        if "Recent updates" in self.browser.title:
            shelf_url = "https://www.goodreads.com/shelf/show/{0}?page={1}"
            for gn in self.query.split(","):
                no_of_shelves = math.ceil(int(self.max_recs)/50) + 1
                for p in range(1, no_of_shelves):
                    html_file = "shelf_{0}_p{1}.html".format(gn, p)
                    crawled_files.append(html_file)
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
        try:
            s = dt_str.strip()
            pub_dt = s[s.find("Published")+9:s.find("by")].strip()
        except AttributeError:
            log("\t**** Could not find publish date.")
        return pub_dt

    def _try_get_item(self, soup, sel):
        val = "--"
        try:
            val = soup.select(sel)[0].text.strip()
        except Exception:
            log("**** Failed to get value for "+sel)
        return val

    def _get_book_detail(self, url):
        book_info = {"book_format": "--", "pages": "--", "synopsis": "--",
                     "isbn": "--", "language": "--", "pub_year": "--",
                     "url": url, "avg_rating": "--", "ratings": "--",
                     "reviews": "--", "author": "--", "title": "--"}

        # https://www.goodreads.com/book/show/6708.The_Power_of_Now
        soup = None

        file_name = "".join(url.split("/"))+".html"
        if self.use_cached_books and self._is_cached(file_name):
            log("Using cached file "+file_name)
            html = self._get_cache_page(file_name)
            soup = BeautifulSoup(html, "lxml")
        else:
            page_url = "https://www.goodreads.com"+url
            page = make_http_request(page_url)
            if page.status_code == requests.codes.ok:
                self._cache_page(file_name, str(page.content, encoding="utf8"))
                soup = BeautifulSoup(page.content, 'lxml')
            else:
                log("Failed to get page at URL {0}. Error: {1}".format(
                    page_url, page.reason))

        if not soup:
            return book_info

        book_info["avg_rating"] = self._try_get_item(
            soup, "#bookMeta > span:nth-child(2)")
        book_info["ratings"] = self._try_get_item(
            soup, "a.gr-hyperlink:nth-child(7)")
        book_info["reviews"] = self._try_get_item(
            soup, "a.gr-hyperlink:nth-child(9)")
        book_info["author"] = self._try_get_item(
            soup, "#bookAuthors > span:nth-child(2)")
        book_info["title"] = self._try_get_item(soup, "#bookTitle")

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
            book_info["pub_year"] = self._get_pub_date(
                pub_yr[0].text) if pub_yr else "--"

            book_info["synopsis"] = self._try_get_item(
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
                books_count.val += 1
                log("Processed {0} books.".format(books_count.val))
            except Exception as ex:
                msg = str(ex)
                log("Error in getting book info: "+msg+". Continuing.")
                if DEBUG:
                    traceback.print_exc()
                if "ConnectionResetError" in msg:
                    log("Waiting for 15s before attempting next request.")
                    time.sleep(15)

    def scrape_goodreads_books(self):
        bc = Obj()
        try:
            crawled_files = self._crawl_goodreads_shelves()
            fn = "_".join(self.query.strip().split(","))\
                .replace(" ", "_")+"_GOODREADS.csv"
            out_file = "{0}/{1}".format(self.out_dir, fn)

            with open(out_file, "w", newline='') as csvfile:
                dw = csv.DictWriter(csvfile, ROW_KEYS, extrasaction='ignore')
                dw.writeheader()
                csvfile.flush()
                shelf_pages = []
                for file_name in crawled_files:
                    # File name is like: "shelf_{0}_p{1}.html"
                    shelf_pages.extend(
                        glob.glob("{0}/{1}".format(self.html_dir, file_name)))

                for h in shelf_pages:
                    log("Extracting data from {0}".format(h))
                    # "/parent/path/shelf_{1}_p{2}.html"
                    gnr = h.split("/")[-1].split("_")[1]
                    with open(h, 'r') as fp:
                        soup = BeautifulSoup(fp, 'lxml')

                    self._extract_books_from_shelf(
                        gnr, dw, soup, books_count=bc)
                    csvfile.flush()

        except Exception as ex:
            log("Error occurred when crawing: "+str(ex))
            traceback.print_exc()
        except KeyboardInterrupt:
            log("Exiting on user request (pressed Ctrl+C)")
        log("Total books = "+str(bc.val))

    def _extract_gs_data(self, html):
        soup = BeautifulSoup(html, "lxml")
        items = soup.select("#gs_res_ccl_mid > div.gs_r.gs_or.gs_scl")

        data = []
        for obj in items:
            title = self._try_get_item(obj, "h3")
            temp = self._try_get_item(obj, "div.gs_ri > div.gs_a")
            authors = temp[:temp.index("-")]
            pub = temp[temp.index("-")+1:]
            abst = self._try_get_item(obj, "div.gs_ri > div.gs_rs")
            cited_by = self._try_get_item(obj,
                                          "div.gs_ri > div.gs_fl > a:nth-child(3)").replace("Cited by ", "")
            url = obj.select_one("div.gs_ggs.gs_fl > div > div > a")
            url = url["href"] if url else "--"
            data.append({"title": title, "author": authors, "publication": pub,
                         "citedby": cited_by, "url": url, "abstract": abst})
        return data

    def screape_google_scholar(self):
        log("Starting webdriver...")
        self._init_selinium()
        try:
            timeout = 5  # 5 sec
            for q in self.query.split(","):
                csv_path = self.out_dir + "/" + q.strip().replace(" ", "_")+"_gs.csv"
                with open(csv_path, "w", newline='') as csvfile:
                    dw = csv.DictWriter(csvfile, GS_ROW_KEYS,
                                        extrasaction='ignore')
                    dw.writeheader()
                    csvfile.flush()
                    pg_url = "https://scholar.google.com"
                    self.browser.get(pg_url)
                    WebDriverWait(self.browser, timeout).until(
                        EC.presence_of_element_located((By.ID, 'gs_hdr_tsi')))
                    log("Loaded Google Scholar page.")
                    query = self.browser.find_element_by_id("gs_hdr_tsi")
                    query.send_keys(q)
                    self.browser.find_element_by_id("gs_hdr_tsb").click()
                    log("Sent search query to website.")
                    WebDriverWait(self.browser, timeout).until(
                        EC.presence_of_element_located((By.CLASS_NAME, 'gs_ab_mdw')))
                    has_next = True
                    rec_count = 0
                    while has_next and rec_count < self.max_recs:
                        time.sleep(2)
                        html_source = self.browser.page_source
                        try:
                            data = self._extract_gs_data(html_source)
                            rec_count += len(data)
                        except Exception as ex:
                            traceback.print_exc()
                            log("Error when extracting information from page. "+str(ex))

                        try:
                            nb = self.browser.find_element_by_link_text("Next")
                            if nb:
                                log("Going to next page...")
                                nb.click()
                                WebDriverWait(self.browser, timeout). \
                                    until(EC.presence_of_element_located(
                                        (By.CLASS_NAME, 'gs_ico_nav_next')))

                            else:
                                has_next = False
                        except Exception as ex:
                            has_next = False
                            traceback.print_exc()
                            log("Error when paginating to next. "+str(ex))

                        dw.writerows(data)
                        csvfile.flush()
        except Exception as ex:
            traceback.print_exc()
        finally:
            self.browser.close()


def main():
    try:
        parser = argparse.ArgumentParser()
        parser.add_argument("data_src", type=str, choices=["scholar", "goodreads"],
                            help="Which source of data to work with.")
        parser.add_argument("out_dir", type=str,
                            help="Output will be written to this directory.")
        parser.add_argument("browser", type=str, choices=["chrome", "firefox", "safari", "edge"],
                            help="Web browser to use.")
        parser.add_argument("pps", type=int,
                            help="Max. books/articles to fetch.")
        parser.add_argument("-q", "--query", type=str,
                            dest="query", help="""
                            Query string to use for Google Scholar. Multiple queries
                            can be supplied as comma-separated list.
                            Required only when data source is scholar.
                            """)
        parser.add_argument("-d", "--html-dir", type=str,
                            dest="html_dir", help="HTML files directory path. Required only when data source is goodreads.")
        parser.add_argument("-g", "--genre-list", type=str,
                            dest="genre_list", help="Comma separated list of genre names. Required only for remote crawling case. Required only when data source is goodreads.")
        parser.add_argument("-v", "--verbose", type=bool, nargs='?',
                            const=True, default=False,
                            dest="verbose", help="Print debug information.")

        args = parser.parse_args()
        if args.verbose:
            global DEBUG
            DEBUG = True
        if "no" == overwrite_existing_path(args.out_dir):
            log("User declined to overwrite output {0}. Aborting.".format(
                args.out_dir))
            return
        Path(args.out_dir).mkdir(parents=True, exist_ok=True)
        if "goodreads" == args.data_src:
            if not (args.genre_list and args.html_dir):
                log("Please supply required parameters: genre list and html directory.")
                return
            oep = overwrite_existing_path(args.html_dir, "[yes/no/merge]")
            if "no" == oep:
                log("User declined to overwrite directory {0}. Aborting.".format(
                    args.html_dir))
                return

            Path(args.html_dir).mkdir(parents=True, exist_ok=True)
            scr = BookScraper(args.browser, args.pps,
                              args.genre_list, args.html_dir, overwrite=oep)
            scr.scrape_goodreads_books()
        else:
            scr = BookScraper(args.browser, args.pps, args.query)
            scr.screape_google_scholar()

    except Exception as ex:
        log("Exiting. Error occurred. "+str(ex))


if __name__ == "__main__":
    main()
