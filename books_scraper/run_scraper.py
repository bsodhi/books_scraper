import os
import sys
# Allows importing from: ../../
parent = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
print("In [{0}], appending [{1}] to system path.".format(__file__, parent))
sys.path.append(parent)
import books_scraper.scraper as SCR
import traceback
import json
import argparse


def main(cfg):
    gr_login = cfg["gr_login"]
    gr_password = cfg["gr_password"]
    scholar_id = "{0}@gmail.com".format(cfg["scholar_id"])
    scholar_password = cfg["scholar_password"]

    html_dir = cfg["html_dir"]
    data_src = cfg["data_src"]
    max_recs = cfg["max_recs"]
    query = cfg["query"]
    out_dir = cfg["out_dir"]
    use_cached_books = cfg["ucb"]
    timeout = cfg["timeout"]

    SCR.log("Starting scraper.")
    bs = SCR.BookScraper(query, max_recs=max_recs, html_dir=html_dir,
                     gr_login=gr_login, gr_password=gr_password,
                     out_dir=out_dir, use_cached_books=use_cached_books,
                     timeout=timeout, scholar_id=scholar_id,
                     scholar_password=scholar_password)
    try:
        if "goodreads" == data_src:
            bs.scrape_goodreads_books()
        elif "scholar" == data_src:
            bs.screape_google_scholar_paged()
        else:
            SCR.log(" Unsupported data source: "+data_src)

        SCR.log("Scraping completed.")
    except Exception as ex:
        SCR.log("Error occurred when scraping data: "+str(ex))
        traceback.print_exc()
    finally:
        pid_file = os.path.join(out_dir, "pid")
        if os.path.exists(pid_file):
            os.remove(pid_file)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("cfg_file", type=str, help="Config file path.")
    parser.add_argument("timeout", type=int, help="Scraping request timeout.")
    parser.add_argument("query", type=str, help="Query string.")
    parser.add_argument("max_recs", type=int,
                        help="Max. no. of records to fetch.")
    parser.add_argument("data_src", type=str, choices=["scholar", "goodreads"],
                        help="Which source of data to work with.")
    parser.add_argument("out_dir", type=str, help="Output directory path.")
    parser.add_argument("html_dir", type=str, help="HTML directory path.")
    parser.add_argument(
        "ucb", type=bool, help="Use cached books.", default=True)

    args = parser.parse_args()
    argdict = vars(args)
    SCR.log("Args: "+str(argdict))
    with open(args.cfg_file, "r") as cfg_file:
        cfg = json.load(cfg_file)
        cfg.update(argdict)

    main(cfg)
