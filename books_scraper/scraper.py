"""
Written with a lot of help from StackOverflow community 
and Python API documentation. Greatly appreciated!
"""
import os
import glob
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
    print("[{0}] : {1}".format(ts, msg))


def debug(msg):
    if DEBUG:
        log(msg)


def start_selenium(web_browser, html_dir, genre_list, pps, overwrite="merge"):
    gr_user = input("Goodreads login ID (an email address): ")
    gr_pass = getpass(prompt="Password: ")
    log("Starting webdriver...")
    if "chrome" == web_browser:
        browser = webdriver.Chrome()
    elif "firefox" == web_browser:
        from selenium.webdriver.firefox.options import Options
        opt = Options()
        opt.headless = True
        browser = webdriver.Firefox(options=opt)
    elif "safari" == web_browser:
        browser = webdriver.Safari()
    elif "edge" == web_browser:
        browser = webdriver.Edge()
    else:
        raise Exception("Unsupported browser: "+web_browser)
    login_url = "https://www.goodreads.com/user/sign_in"
    browser.get(login_url)
    log("Loaded login page.")
    username = browser.find_element_by_id("user_email")
    password = browser.find_element_by_id("user_password")
    username.send_keys(gr_user)
    password.send_keys(gr_pass)

    # username.send_keys("wenox85809@hxqmail.com")
    # password.send_keys("chamanLAL")
    browser.find_element_by_name("sign_in").submit()
    log("Sent login request to website.")
    delay = 5  # seconds
    try:
        myElem = WebDriverWait(browser, delay).until(
            EC.presence_of_element_located((By.CLASS_NAME, 'siteHeader__personal')))
        log("Loaded the user home page.")
        print(browser.title)
    except Exception:
        log("Failed to login.")
        raise

    if "Recent updates" in browser.title:
        shelf_url = "https://www.goodreads.com/shelf/show/{0}?page={1}"
        for gn in genre_list.split(","):
            for p in range(1, int(pps) + 1):
                out_file = "{0}/{1}_p{2}.html".format(html_dir, gn, p)
                url = shelf_url.format(gn, p)
                if overwrite == "merge" and os.path.exists(out_file):
                    log("Page {0} already downloaded. Skipping to next.".format(url))
                    continue
                time.sleep(2)
                log("Fetching ["+url+"]")
                browser.get(url)
                html_source = browser.page_source
                with open(out_file, "w") as html:
                    html.write(html_source)
                    log("Saved HTML at: "+html.name)
        log("Closing the browser")
        browser.close()
    else:
        raise Exception("Failed to load the landing page.")


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


def make_file_soup(html_file):
    with open(html_file) as fp:
        return BeautifulSoup(fp, 'lxml')


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
            soup, "div#description.readable.stacked > span:nth-child(2)")
        book_info["url"] = url
        return book_info
    else:
        return book_info


def extract_data(genre, writer, soup, books_count):
    sel = ".mainContent .leftContainer .elementList"
    for n in soup.select(sel):
        try:
            book = {}
            book["genre"] = genre
            book_url = n.find("a", {"class": "bookTitle"})["href"]
            book.update(get_book_detail(book_url))
            writer.writerow(book)
            books_count.val += 1
            print("Processed {0} books.".format(books_count.val))
        except Exception as ex:
            msg = str(ex)
            log("Error in getting book info: "+msg+". Continuing.")
            if DEBUG:
                traceback.print_exc()
            if "ConnectionResetError" in msg:
                log("Waiting for 15s before attempting next request.")
                time.sleep(15)


def crawl(html_dir, out_dir):
    bc = Obj()
    try:
        out_file = "{0}/goodreads.csv".format(out_dir)
        with open(out_file, "w", newline='') as csvfile:
            dw = csv.DictWriter(csvfile, ROW_KEYS, extrasaction='ignore')
            dw.writeheader()
            htmls = glob.glob("{0}/*.html".format(html_dir))
            for h in htmls:
                log("Extracting data from {0}".format(h))
                gnr = h.split("/")[-1].split("_")[0]
                extract_data(gnr, dw, make_file_soup(h), books_count=bc)
                csvfile.flush()

    except Exception as ex:
        log("Error occurred when crawing: "+str(ex))
        traceback.print_exc()
    except KeyboardInterrupt:
        log("Exiting on user request (pressed Ctrl+C)")
    log("Total books = "+str(bc.val))


def overwrite_existing_path(path_str, options=None):
    fo = "yes"
    if os.path.exists(path_str):
        fo = input(
            "Path {0} already exists. Would you like to overwrite it? {1}: ".format(path_str, options if options else "[yes/no]"))

    return fo


def extract_gs_data(html):
    soup = BeautifulSoup(html, "lxml")
    items = soup.select("#gs_res_ccl_mid > div.gs_r.gs_or.gs_scl")

    data = []
    for obj in items:
        title = _try_get_item(obj, "h3")
        temp = _try_get_item(obj, "div.gs_ri > div.gs_a")
        authors = temp[:temp.index("-")]
        pub = temp[temp.index("-")+1:]
        abst = _try_get_item(obj, "div.gs_ri > div.gs_rs")
        cited_by = _try_get_item(obj,
                                 "div.gs_ri > div.gs_fl > a:nth-child(3)").replace("Cited by ", "")
        url = obj.select_one("div.gs_ggs.gs_fl > div > div > a")
        url = url["href"] if url else "--"
        data.append({"title": title, "author": authors, "publication": pub,
                     "citedby": cited_by, "url": url, "abstract": abst})
    return data


def start_selenium_gs(web_browser, query_str, out_dir, max_records=100):
    log("Starting webdriver...")
    if "chrome" == web_browser:
        browser = webdriver.Chrome()
    elif "firefox" == web_browser:
        from selenium.webdriver.firefox.options import Options
        opt = Options()
        opt.headless = True
        browser = webdriver.Firefox(options=opt)
    elif "safari" == web_browser:
        browser = webdriver.Safari()
    elif "edge" == web_browser:
        browser = webdriver.Edge()
    else:
        raise Exception("Unsupported browser: "+web_browser)
    try:
        for q in query_str.split(","):
            csv_path = out_dir + "/" + q.strip().replace(" ", "_")+"_gs.csv"
            with open(csv_path, "w", newline='') as csvfile:
                dw = csv.DictWriter(csvfile, GS_ROW_KEYS,
                                    extrasaction='ignore')
                dw.writeheader()
                pg_url = "https://scholar.google.com"
                browser.get(pg_url)
                log("Loaded Google Scholar page.")
                query = browser.find_element_by_id("gs_hdr_tsi")
                query.send_keys(q)
                browser.find_element_by_id("gs_hdr_tsb").click()
                log("Sent search query to website.")
                has_next = True
                rec_count = 0
                while has_next and rec_count < max_records:
                    time.sleep(2)
                    html_source = browser.page_source
                    data = extract_gs_data(html_source)
                    rec_count += len(data)
                    nb = browser.find_element_by_link_text("Next")
                    if nb:
                        log("Going to next page...")
                        nb.click()
                    else:
                        has_next = False
                    dw.writerows(data)
                    csvfile.flush()
    except Exception as ex:
        traceback.print_exc()
    finally:
        browser.close()


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
                            help="No. of pages per shelf or Max. records in the Google Scholar query result.")
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
                args.out_file))
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
            # Start the Selenium session
            start_selenium(args.browser, args.html_dir,
                           args.genre_list, args.pps, overwrite=oep)
            crawl(args.html_dir, args.out_dir)
        else:
            start_selenium_gs(args.browser, args.query,
                              args.out_dir, max_records=args.pps)

    except Exception as ex:
        log("Exiting. Error occurred. "+str(ex))


if __name__ == "__main__":
    main()
