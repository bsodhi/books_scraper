from flask import Flask, abort, session, redirect, url_for, request, render_template
from markupsafe import escape
from subprocess import Popen
import os
import sqlite3
import random
import string
import argparse
import glob
import shutil
from pathlib import Path
from getpass import getpass
from flask.helpers import send_file
from datetime import datetime as DT

app = Flask(__name__)


def get_ts_str():
    return DT.now().strftime("%Y%m%d_%H%M%S")


def random_str(size=10):
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=size))


def _init_db():
    try:
        with sqlite3.connect('app.db') as conn:
            c = conn.cursor()
            # Create table
            c.execute('''CREATE TABLE IF NOT EXISTS users
                (id INTEGER PRIMARY KEY AUTOINCREMENT, login_id text, 
                pass_hashed text, full_name text, role text)''')
            conn.commit()
        print("DB initialized.")
    except Exception as ex:
        pass


def _authenticate(login_id, pass_hashed):
    valid = False
    try:
        with sqlite3.connect('app.db') as conn:
            c = conn.cursor()
            # Create table
            c.execute('SELECT * FROM users WHERE login_id=? and pass_hashed=?',
                      (login_id, pass_hashed))
            if c.fetchone():
                valid = True
    except Exception as ex:
        print("*** Error occurred: "+str(ex))
    return valid


def _add_user(login_id, pass_hashed, full_name, role="USER"):
    try:
        with sqlite3.connect('app.db') as conn:
            c = conn.cursor()
            # Create table
            c.execute("""INSERT INTO users(login_id, pass_hashed, full_name, role)
            VALUES (?,?,?,?)""", (login_id, pass_hashed, full_name, role))
            conn.commit()
    except Exception as ex:
        pass


@app.route('/start', methods=['GET', 'POST'])
def start():

    if "login_id" not in session:
        print("Illegal access to operation. Login required.")
        return redirect(url_for('login'))
    print(request.form)
    login_id = session['login_id']
    out_dir = "{0}/{1}/{2}".format(os.getcwd(), login_id, get_ts_str())
    Path(out_dir).mkdir(parents=True, exist_ok=True)
    print("Starting command in: "+os.getcwd())
    data_src = request.form['data_src']
    max_rec = request.form['max_rec']
    query = request.form['query']
    html_dir = "{0}/html/".format(out_dir)

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
    print("Starting command: "+cmd)
    Popen([cmd], shell=True, stdin=None,
          stdout=None, stderr=None, close_fds=True)
    return redirect(url_for('task_status'))


@app.route('/signup', methods=['POST', 'GET'])
def signup():
    error = None
    if request.method == 'POST':
        _add_user(request.form['login_id'],
                  request.form['password'], request.form['full_name'])
        return render_template("home.html", name=request.form['full_name'])

    # the code below is executed if the request method
    # was GET or the credentials were invalid
    return render_template('signup.html', error=error)


@app.route('/login', methods=['POST', 'GET'])
def login():
    error = None
    if request.method == 'POST':
        if _authenticate(request.form['login_id'],
                         request.form['password']):
            print("Login successful.")
            session['login_id'] = request.form['login_id']
            return redirect(url_for('home'))
        else:
            error = 'Invalid username/password'
    # the code below is executed if the request method
    # was GET or the credentials were invalid
    return render_template('index.html', error=error)


def _fmt_date_str(dt_str):
    try:
        d2 = DT.strptime(dt_str, "%Y%m%d_%H%M%S")
        return d2.strftime("%Y-%b-%d@%H:%M:%S")
    except Exception as ex:
        print("*** Failed to format date: "+str(ex))
        return dt_str


@app.route('/status')
def task_status():
    if "login_id" not in session:
        print("Illegal access to operation. Login required.")
        return redirect(url_for('login'))

    path = "{0}/{1}".format(os.getcwd(), session['login_id'])
    if os.path.exists(path):
        subfolders = [f.path for f in os.scandir(path) if f.is_dir()]
        subfolders.sort(reverse=True)
        data = [
            {"folder": d.split("/")[-1],
             "folder_label": _fmt_date_str(d.split("/")[-1]),
             "files": [f.path for f in os.scandir(d) if f.is_file()]
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
        print("Illegal access to operation. Login required.")
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
        print("Illegal access to operation. Login required.")
        return redirect(url_for('login'))

    print("dir_path = "+dir_path)
    if "/" in dir_path or ".." in dir_path:
        print("!!! Invalid path: "+dir_path)
        return abort(401)
    else:
        base_path = "{0}/{1}".format(os.getcwd(), session['login_id'])
        abs_path = os.path.join(base_path, dir_path)
        print("!!! Deleting: "+abs_path)
        shutil.rmtree(abs_path)
        return redirect(url_for('task_status'))


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/home')
def home():
    if "login_id" not in session:
        print("Illegal access to operation. Login required.")
        return redirect(url_for('login'))
    return render_template('home.html', name=escape(session['login_id']))


@app.route('/logout')
def logout():
    # remove the username from the session if it's there
    session.pop('login_id', None)
    return redirect(url_for('index'))


gr_login = None
gr_password = None


if __name__ == "__main__":
    app.secret_key = random_str(size=30)
    if not gr_login:
        gr_login = input("Goodreads login ID: ")
        gr_password = getpass(prompt="Goodreads password: ")
    app.run(host="0.0.0.0", port=5500)
    _init_db()
