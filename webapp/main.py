from flask import Flask, abort, session, redirect, url_for, request, render_template
from flask.blueprints import Blueprint
import views as V
import argparse
import json
import logging

app = Flask(__name__)
app.register_blueprint(V.vbp, url_prefix='/books')

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("-d", "--debug", type=bool, nargs='?',
                        const=True, default=False,
                        dest="debug", help="Run the server in debug mode.")
    parser.add_argument("cfg_file_path", type=str,
                        help="Scrapper runner config file path.")
    args = parser.parse_args()
    app.secret_key = V.random_str(size=30)
    V._init_db()

    with open(args.cfg_file_path, "r") as cfg_file:
        V.CONFIG = json.load(cfg_file)

    logging.info("CONFIG: "+str(V.CONFIG))

    app.run(host=V.CONFIG["host"],
            port=V.CONFIG["port"],
            threaded=True,
            # ssl_context=(V.CONFIG["ssl_cert_file"], V.CONFIG["ssl_key_file"]),
            debug=args.debug)

