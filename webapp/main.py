from flask import Flask, abort, session, redirect, url_for, request, render_template
from markupsafe import escape
from subprocess import Popen
import os
import sqlite3
import random
import string
import argparse
import traceback
import glob
import shutil
import logging
from passlib.hash import pbkdf2_sha256
from pathlib import Path
from getpass import getpass
from flask.helpers import send_file
from datetime import datetime as DT
import signal

app = Flask(__name__)
logging.basicConfig(filename='scraper.log', level=logging.INFO)


def get_ts_str():
    return DT.now().strftime("%Y%m%d_%H%M%S")


def random_str(size=10):
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=size))


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


@app.route('/start', methods=['GET', 'POST'])
def start():

    if "login_id" not in session:
        logging.warning("Illegal access to operation. Login required.")
        return redirect(url_for('login'))

    login_id = session['login_id']
    out_dir = "{0}/{1}/{2}".format(os.getcwd(), login_id, get_ts_str())
    Path(out_dir).mkdir(parents=True, exist_ok=True)
    logging.info("Starting command in: "+os.getcwd())
    data_src = request.form['data_src']
    max_rec = request.form['max_rec']
    query = request.form['query']
    html_dir = "{0}/html/".format(os.getcwd())

    cmd_args = []
    cmd_args.append(data_src)
    cmd_args.append(max_rec)
    cmd_args.append("\""+query+"\"")
    cmd_args.append(html_dir if html_dir else "none")
    cmd_args.append(out_dir)
    cmd_args.append(gr_login if data_src == "goodreads" else "none")
    cmd_args.append(gr_password if data_src == "goodreads" else "none")
    cmd_args.append(" > {0}/task.log".format(out_dir))

    mydir = os.getcwd()
    cmd = "python {0}/books_scraper/run_scraper.py {1}".format(
        mydir, " ".join(cmd_args))
    logging.info("Starting command: "+cmd)
    proc = Popen([cmd], shell=True, stdin=None,
                 stdout=None, stderr=None, close_fds=True)
    pid_file = os.path.join(out_dir, "pid")
    with open(pid_file, "w") as pf:
        pf.write(str(proc.pid))
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


@app.route('/status')
def task_status():
    if "login_id" not in session:
        logging.warning("Illegal access to operation. Login required.")
        return redirect(url_for('login'))

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
def get_file(file_path):
    if "login_id" not in session:
        logging.warning("Illegal access to operation. Login required.")
        return redirect(url_for('login'))

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
def clear_dir(dir_path):
    if "login_id" not in session:
        logging.warning("Illegal access to operation. Login required.")
        return redirect(url_for('login'))

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


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/home')
def home():
    if "login_id" not in session:
        logging.warning("Illegal access to operation. Login required.")
        return redirect(url_for('login'))
    pids = _existing_tasks(session['login_id'])
    return render_template('home.html',
                           name=escape(session['login_id']), pids=pids)


@app.route('/logout')
def logout():
    # remove the username from the session if it's there
    session.pop('login_id', None)
    return redirect(url_for('index'))


gr_login = None
gr_password = None


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("-p", "--port-no", type=int, default=5500,
                        dest="port", help="Port number.")
    parser.add_argument("-t", "--host", type=str, default="0.0.0.0",
                        dest="host", help="Host")
    parser.add_argument("-d", "--debug", type=bool, nargs='?',
                        const=True, default=False,
                        dest="debug", help="Run the server in debug mode.")
    parser.add_argument("login", type=str,
                        help="Goodreads login ID")
    parser.add_argument("password", type=str,
                        help="Goodreads password.")
    args = parser.parse_args()
    gr_login = args.login
    gr_password = args.password
    app.secret_key = random_str(size=30)
    _init_db()
    app.run(host=args.host, port=args.port,
            ssl_context='adhoc', debug=args.debug)
