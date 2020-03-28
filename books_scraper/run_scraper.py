import sys
import traceback
import os
from scraper import *

log("Scraper invoked as: "+ str(sys.argv[:-1])+ " ****")

if len(sys.argv) != 10:
    log("Could not process request. Required 10 arguments supplied {0}."
        .format(len(sys.argv)))
    exit(-1)

data_src = sys.argv[1]
max_recs = sys.argv[2]
query = sys.argv[3]
html_dir = sys.argv[4]
out_dir = sys.argv[5]
use_cached_books = sys.argv[6]
timeout = int(sys.argv[7])
gr_login = sys.argv[8]
gr_password = sys.argv[9]


log("Starting scraper.")
bs = BookScraper("firefox", max_recs, query, html_dir=html_dir,
                 gr_login=gr_login, gr_password=gr_password,
                 out_dir=out_dir, use_cached_books=use_cached_books,
                 timeout=timeout)
try:
    if "goodreads" == data_src:
        bs.scrape_goodreads_books()
    elif "scholar" == data_src:
        bs.screape_google_scholar()
    else:
        log(" Unsupported data source: "+data_src)

    log("Scraping completed.")
except Exception as ex:
    log("Error occurred when scraping data: "+str(ex))
    traceback.print_exc()
finally:
    os.remove(os.path.join(out_dir, "pid"))
