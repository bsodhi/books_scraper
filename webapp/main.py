from werkzeug.utils import secure_filename
from datetime import datetime as DT
from flask.helpers import flash, send_file
from getpass import getpass
from pathlib import Path
from passlib.hash import pbkdf2_sha256
from subprocess import Popen
from markupsafe import escape
from functools import wraps
from flask import Flask, abort, session, redirect, url_for, request, render_template
# from concurrent.futures.process import ProcessPoolExecutor
import os
import sys
import json
import signal
import logging
import shutil
import glob
import traceback
import argparse
import string
import random
import sqlite3
import concurrent.futures
# Allows importing from: ../../
parent = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
print("In [{0}], appending [{1}] to system path.".format(__file__, parent))
sys.path.append(parent)
if parent:
    import books_scraper.scraper as SCR

UPLOAD_FOLDER = os.path.join(os.getcwd(), "gs_uploads")
HTML_DIR = "{0}/html/".format(os.getcwd())
Path(HTML_DIR).mkdir(parents=True, exist_ok=True)

app = Flask(__name__)
app.config['APPLICATION_ROOT'] = '/books'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
logging.basicConfig(filename='scraper.log', level=logging.INFO)
Path(UPLOAD_FOLDER).mkdir(parents=True, exist_ok=True)

# PPE = ProcessPoolExecutor(max_workers=5)
TPE = concurrent.futures.ThreadPoolExecutor(max_workers=5)


def get_ts_str():
    return DT.now().strftime("%Y%m%d_%H%M%S")


def random_str(size=10):
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=size))


def auth_check(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if "login_id" not in session:
            logging.warning("Illegal access to operation. Login required.")
            return redirect(url_for('login'))
        else:
            logging.info("User is authenticated already.")
        return f(*args, **kwargs)
    return wrapper


def _init_db():
    with sqlite3.connect('app.db') as conn:
        c = conn.cursor()
        # Create table
        c.execute('''CREATE TABLE IF NOT EXISTS users
            (id INTEGER PRIMARY KEY AUTOINCREMENT, 
            login_id text NOT NULL UNIQUE, 
            pass_hashed text NOT NULL, full_name text NOT NULL, 
            role text NOT NULL)''')
        conn.commit()
        logging.info("DB initialized.")


def _authenticate(login_id, plain_pass):
    valid = False
    try:
        with sqlite3.connect('app.db') as conn:
            c = conn.cursor()
            # Create table
            c.execute(
                'SELECT pass_hashed FROM users WHERE login_id=?', (login_id,))
            row = c.fetchone()
            if row:
                valid = pbkdf2_sha256.verify(plain_pass, row[0])
    except Exception as ex:
        logging.exception("Error occurred when authenticating.")
    return valid


def _add_user(login_id, pass_hashed, full_name, role="USER"):
    with sqlite3.connect('app.db') as conn:
        c = conn.cursor()
        c.execute('SELECT count(*) FROM users WHERE login_id=?', (login_id,))
        if c.fetchone()[0] != 0:
            raise Exception("Login ID already exists.")
        c.execute("""INSERT INTO users(login_id, pass_hashed, full_name, role)
        VALUES (?,?,?,?)""", (login_id, pass_hashed, full_name, role))
        conn.commit()


def _scrape_goodreads(query, max_rec, out_dir, dont_ucb, login_id):
    pid_file = os.path.join(out_dir, "pid")
    SCR.LOG_FILE = os.path.join(out_dir, "task.log")
    try:
        with open(pid_file, "w") as pif:
            pif.write(query)

        bs = SCR.BookScraper(query,
                             max_recs=max_rec,
                             use_cached_books=not dont_ucb,
                             out_dir=out_dir,
                             html_dir=HTML_DIR,
                             gr_login=CONFIG["gr_login"],
                             gr_password=CONFIG["gr_password"],
                             web_browser=CONFIG["browser"],
                             timeout=CONFIG["timeout"],
                             http_delay_sec=CONFIG["http_delay_sec"])
        bs.scrape_goodreads_books()

    except Exception as ex:
        msg = "Error occurred when processing googreads scraping."
        logging.exception(msg)
        return render_template("home.html", error=msg,
                               name=escape(session['login_id']))
    finally:
        try:
            if os.path.exists(pid_file):
                os.remove(pid_file)
            logging.info("Closed pending task for user "+login_id)
        except Exception as ex2:
            logging.exception("Failed to close the task.")


def _fmt_date_str(dt_str):
    try:
        d2 = DT.strptime(dt_str, "%Y%m%d_%H%M%S")
        return d2.strftime("%Y-%b-%d@%H:%M:%S")
    except Exception as ex:
        logging.exception("Failed to format date.")
        return dt_str


def _existing_tasks(login_id):
    base_path = os.path.join(os.getcwd(), session['login_id'])
    pid_files = glob.glob("{0}/**/pid".format(base_path))
    pids = []
    for pfile in pid_files:
        with open(pfile, "r") as pf:
            pids.append(pf.read())
    return pids


@app.route('/start', methods=['GET', 'POST'])
@auth_check
def start():
    login_id = session['login_id']
    out_dir = os.path.join(os.getcwd(), login_id, get_ts_str())
    Path(out_dir).mkdir(parents=True, exist_ok=True)

    logging.info("Starting command in: "+os.getcwd())
    max_rec = request.form['max_rec']
    query = request.form['query']
    timeout = request.form['timeout']
    dont_ucb = request.form.get('dont_ucb') == "on"
    TPE.submit(_scrape_goodreads, query, max_rec, out_dir, dont_ucb, login_id)

    return redirect(url_for('task_status'))


@app.route('/status')
@auth_check
def task_status():
    path = "{0}/{1}".format(os.getcwd(), session['login_id'])
    if os.path.exists(path):
        subfolders = [f.path for f in os.scandir(path) if f.is_dir()]
        subfolders.sort(reverse=True)
        data = [
            {"folder": d.split("/")[-1],
             "folder_label": _fmt_date_str(d.split("/")[-1]),
             "files": [f.path for f in os.scandir(d) if f.is_file()],
             "status": "RUNNING" if glob.glob(d+"/pid") else "FINISHED",
             } for d in subfolders]
    else:
        data = []

    return render_template('status.html',
                           data=data,
                           out_dir=path,
                           name=escape(session['login_id']))


@app.route('/', defaults={'file_path': ''})
@app.route('/<path:file_path>')
@auth_check
def get_file(file_path):
    base_path = "{0}/{1}".format(os.getcwd(), session['login_id'])
    abs_path = os.path.join(base_path, file_path)

    # Check if path is a file and serve
    if os.path.isfile(abs_path):
        if abs_path.endswith("task.log"):
            with open(abs_path, "r") as logs_file:
                return render_template('show_logs.html',
                                       name=escape(session['login_id']),
                                       data=escape(logs_file.read()))
        else:
            return send_file(abs_path, as_attachment=True)
    else:
        return abort(404)


@app.route('/clear', defaults={'dir_path': ''})
@app.route('/clear/<path:dir_path>')
@auth_check
def clear_dir(dir_path):
    logging.debug("dir_path = "+dir_path)
    if "/" in dir_path or ".." in dir_path:
        logging.error("!!! Invalid path: "+dir_path)
        return abort(401)
    else:
        base_path = "{0}/{1}".format(os.getcwd(), session['login_id'])
        abs_path = os.path.join(base_path, dir_path)
        for pid in _existing_tasks(session['login_id']):
            try:
                os.kill(int(pid), signal.SIGTERM)
            except Exception as ex:
                logging.exception("Error when deleting process.")
        logging.info("!!! Deleting: "+abs_path)
        shutil.rmtree(abs_path)
        return redirect(url_for('task_status'))


@app.route('/signup', methods=['POST', 'GET'])
def signup():
    error = None
    try:
        if request.method == 'POST':
            pw_hashed = pbkdf2_sha256.hash(request.form['password'])
            _add_user(request.form['login_id'], pw_hashed,
                      request.form['full_name'])
            return render_template("index.html",
                                   error="User created. Please login with your credentials.")

    except Exception as ex:
        logging.exception("Error occurred when signing up.")
        error = str(ex)

    return render_template('signup.html', error=error)


@app.route('/login', methods=['POST', 'GET'])
def login():
    error = None
    try:
        if request.method == 'POST':
            if _authenticate(request.form['login_id'],
                             request.form['password']):
                logging.info("Login successful.")
                session['login_id'] = request.form['login_id']
                return redirect(url_for('home'))
            else:
                error = 'Invalid username/password'
    except Exception as ex:
        logging.exception("Error occurred when logging in.")
        error = str(ex)
    # the code below is executed if the request method
    # was GET or the credentials were invalid
    return render_template('index.html', error=error)


@app.route('/')
def index():
    if "login_id" in session:
        return redirect(url_for('home'))
    return render_template('index.html')


@app.route('/gr')
@auth_check
def home():
    pids = _existing_tasks(session['login_id'])
    return render_template('home.html',
                           name=escape(session['login_id']), pids=pids)


@app.route('/logout')
def logout():
    # remove the username from the session if it's there
    session.pop('login_id', None)
    return redirect(url_for('index'))


def _process_zip_upload(file_path, login_id, src_type):
    logging.info("Processing: "+file_path)
    out_dir = "{0}/{1}/{2}".format(os.getcwd(), login_id, get_ts_str())
    Path(out_dir).mkdir(parents=True, exist_ok=True)
    bs = SCR.BookScraper("", html_dir=HTML_DIR, out_dir=out_dir,
                         http_delay_sec=CONFIG["http_delay_sec"])
    bs.extract_from_zip(file_path, src_type)


@app.route('/gs', methods=['GET', 'POST'])
@auth_check
def upload_file():
    login_id = session['login_id']
    logging.info("Upload destination: "+UPLOAD_FOLDER)
    try:
        if request.method == 'POST':
            # check if the post request has the file part
            if 'zip_file' not in request.files:
                logging.info("No file part found in request.")
                return render_template('upload_gs.html',
                                       error="No file part found!",
                                       name=escape(login_id))
            file = request.files['zip_file']
            # if user does not select file, browser also
            # submit an empty part without filename
            if file.filename == '':
                return render_template('upload_gs.html',
                                       error="No file data found!",
                                       name=escape(login_id))
            if file and file.filename.endswith(".zip"):
                sfn = secure_filename(file.filename)
                file_path = os.path.join(app.config['UPLOAD_FOLDER'], sfn)
                file.save(file_path)
                src_type = request.form.get("src_type")
                _process_zip_upload(file_path, login_id, src_type)
                return redirect(url_for('task_status'))
            else:
                logging.error("File type not allowed!")
                return render_template('upload_gs.html',
                                       error="File type not allowed!",
                                       name=escape(login_id))

        else:
            logging.info("GET request for upload.")

        return render_template('upload_gs.html',
                               name=escape(login_id))
    except Exception as ex:
        logging.exception("Error when uploading.")
        return render_template('upload_gs.html', error=str(ex),
                               name=escape(login_id))


def validate_fuzzy_request():
    msg = []
    if 'libcsv' not in request.files or request.files['libcsv'].filename == '':
        msg.append("Library data CSV is missing.")
    if 'grcsv' not in request.files or request.files['grcsv'].filename == '':
        msg.append("Goodreads data CSV is missing.")
    return msg


def _process_fuzzy_match(login_id, fp_gr, fp_lib, score, match_mode):
    from webapp.fuzzy_match import find_fuzz
    try:
        out_file = os.path.join(os.getcwd(), login_id,
                                "{0}_fuzzy_result.csv".format(get_ts_str()))
        log_file = os.path.join(os.getcwd(), login_id,
                                "fuzzy_task.log")
        find_fuzz(fp_gr, fp_lib, score, match_mode,
                  out_file=out_file, log_file=log_file)
        logging.info("Fuzzy check complete.")
    except Exception as ex:
        logging.exception("Error occurred.")


@app.route('/fuzz', methods=['GET', 'POST'])
@auth_check
def fuzzy_check():
    login_id = session['login_id']
    out_dir = os.path.join(os.getcwd(), login_id)
    Path(out_dir).mkdir(parents=True, exist_ok=True)
    logs_file = os.path.join(out_dir, "fuzzy_task.log")
    try:
        if request.method == 'POST':
            msg = validate_fuzzy_request()
            if len(msg) > 0:
                logging.error(". ".join(msg))
                return render_template('fuzzy.html',
                                       error=". ".join(msg),
                                       name=escape(login_id))

            lib_csv, gr_csv = request.files['libcsv'], request.files['grcsv']
            sfn_libcsv = secure_filename(lib_csv.filename)
            sfn_grcsv = secure_filename(gr_csv.filename)

            fp_lib = os.path.join(out_dir, sfn_libcsv)
            lib_csv.save(fp_lib)

            fp_gr = os.path.join(out_dir, sfn_grcsv)
            gr_csv.save(fp_gr)

            match_mode = request.form['match_mode']
            score = request.form['score']

            TPE.submit(_process_fuzzy_match, login_id,
                       fp_gr, fp_lib, score, match_mode)
            return redirect(url_for('fuzzy_check'))

        else:
            logging.info("GET request for upload.")
            res_files = glob.glob("{0}/*_fuzzy_result.csv".format(out_dir))
            return render_template('fuzzy.html', name=escape(login_id),
                                   data=res_files, logs_file=logs_file if Path(logs_file).exists() else None)

    except Exception as ex:
        logging.exception("Error when handling fuzzy check.")
        return render_template('fuzzy.html', error=str(ex),
                               name=escape(login_id),
                               logs_file=logs_file if Path(logs_file).exists() else None)


CONFIG = None

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("-d", "--debug", type=bool, nargs='?',
                        const=True, default=False,
                        dest="debug", help="Run the server in debug mode.")
    parser.add_argument("cfg_file_path", type=str,
                        help="Scrapper runner config file path.")
    args = parser.parse_args()
    app.secret_key = random_str(size=30)
    _init_db()

    with open(args.cfg_file_path, "r") as cfg_file:
        CONFIG = json.load(cfg_file)

    logging.info("CONFIG: "+str(CONFIG))

    app.run(host=CONFIG["host"],
            port=CONFIG["port"],
            threaded=True,
            # ssl_context=(CONFIG["ssl_cert_file"], CONFIG["ssl_key_file"]),
            debug=args.debug)
