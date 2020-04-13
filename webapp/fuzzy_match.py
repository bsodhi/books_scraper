import textdistance as TD
import re
import csv
import argparse
import time
from datetime import datetime as DT
from concurrent.futures.process import ProcessPoolExecutor
from concurrent.futures import as_completed
import queue
import threading
import logging

OUT_CSV_HEADER = ['GR ROW', 'GR AUTHOR', 'GR TITLE',
                  'Lib ROW', 'Lib AUTHOR', 'Lib TITLE',
                  'AUTHOR SCORE', 'TITLE SCORE', 'COMBINED SCORE']

LOG_FILE="fuzzy_task.log"

class Counter():
    val = 0


def clean_str(tok):
    return re.sub('[^A-Za-z0-9]+', ' ', tok)

def log(msg, clear=False):
    with open(LOG_FILE, "w" if clear else "a") as lf:
        now = DT.now().strftime("%d/%m/%Y@%H:%M:%S")
        lf.write("{0}: {1}\n".format(now, msg))

def check_match(data):
    gr_row_no = data["gr_row_no"]
    gr_row = data["gr_row"]
    lib_rows = data["lib_rows"]
    score = int(data["score"])
    match_mode = data["match_mode"].upper().strip()

    matches = []
    for idx, lr in enumerate(lib_rows):
        auth_score = int(TD.jaccard(gr_row["auth_tok"], lr["auth_tok"]) * 100)
        title_score = int(TD.jaccard(gr_row["title_tok"], lr["title_tok"]) * 100)
        gr_comb = gr_row["auth_tok"] + gr_row["title_tok"]
        lr_comb = lr["auth_tok"] + lr["title_tok"]
        total_score = int(TD.jaccard(gr_comb, lr_comb) * 100)
        cond = False

        if match_mode == "TA":
            cond = total_score > score
        elif match_mode == "T":
            cond = title_score > score
        elif match_mode == "TTA":
            cond = title_score > score or total_score > score
        elif match_mode == "A":
            cond = auth_score > score
        else:
            raise Exception("Unsupported matching condition: "+match_mode)
        
        if cond:
            row = dict(zip(OUT_CSV_HEADER,
                           [gr_row_no, gr_row["author"], gr_row["title"],
                            idx, lr['author'], lr['title'],
                            auth_score, title_score, total_score
                            ]))
            matches.append(row)

    return matches


def file_len(fname):
    with open(fname, 'r', encoding='utf8') as f:
        for i, l in enumerate(f):
            pass
    return i + 1


def get_csv_data(file_path):
    data = []
    with open(file_path, "r") as rd_csv:
        rd = csv.DictReader(rd_csv)
        row_no, mc = 1, 0
        for row in rd:
            auth, title = row.get("AUTHOR"), row.get("TITLE")
            auth_tok = clean_str(auth).lower().split()
            title_tok = clean_str(title).lower().split()

            item = {"author": auth, "title": title,
                    "auth_tok": auth_tok, "title_tok": title_tok}
            data.append(item)
    log("Loaded {0} rows from {1}".format(len(data), file_path))
    return data


def find_fuzz(gr_csv_file, lib_csv_file, score, match_mode,
        out_file='results.csv', log_file="fuzzy_task.log"):
    try:
        global LOG_FILE
        LOG_FILE = log_file
        log("Starting new job.", clear=True)
        ref_len = file_len(gr_csv_file)
        log("Total rows in GR CSV={0}".format(ref_len))
        with open(out_file, 'w', newline='') as outcsv:
            writer = csv.DictWriter(outcsv, fieldnames=OUT_CSV_HEADER)
            writer.writeheader()

        q = queue.Queue(maxsize=100)
        threads = []
        th_count = 8
        for i in range(th_count):
            t = threading.Thread(
                name="Th-{0}".format(i), target=worker, args=(q, ))
            t.start()
            threads.append(t)
        log("Initialized threads. Adding rows to worker queue...")

        d1 = get_csv_data(gr_csv_file)
        d2 = get_csv_data(lib_csv_file)

        # We iterate over the smaller list 
        gr_rows = d1 if len(d1) <= len(d2) else d2
        lib_rows = d1 if len(d1) >= len(d2) else d2

        ctr = Counter()
        for i, grr in enumerate(gr_rows):
            q.put({"gr_row_no": i+1, "gr_row": grr,
                "lib_rows": lib_rows, "score": score,
                "match_mode": match_mode, "counter": ctr,
                "total_rows": len(gr_rows), 
                "out_file":out_file})

        # block until all tasks are done
        q.join()

        # stop workers
        for i in range(th_count):
            q.put(None)
        for t in threads:
            t.join()
        
        
        log("Stopped all worker threads.")
    except Exception as ex:
        log("Error occurred: "+str(ex))


def worker(task_queue):
    while True:
        try:
            item = task_queue.get()
            if item is None:
                break
            matches = check_match(item)
            out_file = item.get("out_file")
            with open(out_file, 'a', newline='') as outcsv:
                writer = csv.DictWriter(outcsv, fieldnames=OUT_CSV_HEADER)
                writer.writerows(matches)
            ctr = item.get("counter")
            ctr.val += len(matches)
            task_queue.task_done()
            log("Processed row {0}/{1}. Total matches={2}".format(
                item.get("gr_row_no"), item.get("total_rows"), ctr.val))
        except Exception as ex:
            logging.exception("Error occurred.")

if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="""
    This program prints the fuzzy matches found in two CSV files.
    The two columns 'AUTHOR' and 'TITLE' from both files are used
    for fuzzy comparison. There should not be any spaces around 
    the header column names. The output is written into a file
    named 'results.csv' in the folder where you run this program.
    An existing file with the same name will be overwritten.
    """)
    ap.add_argument("-g", "--gr-data", required=True, dest="goodreads_csv",
                    help="Path to Goodreads data CSV file.")
    ap.add_argument("-l", "--lib-data", required=True, dest="library_csv",
                    help="Path to library CSV file to scan.")
    ap.add_argument("-m", "--match-score", required=True, dest="score",
                    type=int, help="""Threshold of matching 0 - 100. 
                    Two rows are considered a fuzzy match if both
                    the author and title values have a score above
                    this value.""")
    ap.add_argument("-c", "--columns", required=True, dest="columns",
                    type=str, choices=["T", "A", "TA", "TTA"], 
                    help="""Which columns to use for checking a match.
                    T: Only title,
                    A: Only author, 
                    TA: Title plus author,
                    TTA: Title or (title+author).
                    """)
    args = ap.parse_args()
    start_time = time.time()
    find_fuzz(args.goodreads_csv, args.library_csv, args.score, args.columns)
    time_taken = time.strftime(
        "%H:%M:%S", time.gmtime(time.time() - start_time))
    log("Done in "+time_taken)
