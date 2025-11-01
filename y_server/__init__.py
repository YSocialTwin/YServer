import json
import logging
import os
import shutil
import time

from flask import Flask, g, request
from flask_sqlalchemy import SQLAlchemy

log = logging.getLogger('werkzeug')
log.setLevel(logging.WARNING)
db = SQLAlchemy()

try:
    # read the experiment configuration
    config = json.load(open(f"config_files{os.sep}exp_config.json"))

    # create the experiments folder
    if not os.path.exists(f".{os.sep}experiments"):
        os.mkdir(f".{os.sep}experiments")

    if (
        not os.path.exists(f"experiments{os.sep}{config['name']}.db")
        or config["reset_db"] == "True"
    ):
        # copy the clean database to the experiments folder
        shutil.copyfile(
            f"data_schema{os.sep}database_clean_server.db",
            f"experiments{os.sep}{config['name']}.db",
        )

    app = Flask(__name__)
    app.config["SECRET_KEY"] = "4YrzfpQ4kGXjuP6w"
    app.config[
        "SQLALCHEMY_DATABASE_URI"
    ] = f"sqlite:///../experiments/{config['name']}.db"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    db = SQLAlchemy(app)

    # Log the request duration
    @app.before_request
    def start_timer():
        g.start_time = time.time()


    @app.after_request
    def log_request(response):
        if hasattr(g, 'start_time'):
            from y_server.modals import Rounds
            from sqlalchemy import desc
            
            duration = time.time() - g.start_time
            log = {
                "remote_addr": request.remote_addr,
                "method": request.method,
                "path": request.path,
                "status_code": response.status_code,
                "duration": round(duration, 4),
                "time": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
            }
            
            # Add current round information from the database
            try:
                current_round = Rounds.query.order_by(desc(Rounds.id)).first()
                if current_round:
                    log["tid"] = current_round.id
                    log["day"] = current_round.day
                    log["hour"] = current_round.hour
            except:
                # If there's an error querying the database, continue without round info
                pass

            logging.info(log)
        return response

except:  # Y Web subprocess
    # base path
    BASE_DIR = os.path.dirname(os.path.abspath(__file__)).split("y_server")[0]

    # create the experiments folder
    if not os.path.exists(f"{BASE_DIR}experiments"):
        os.mkdir(f"{BASE_DIR}experiments")
        shutil.copyfile(
            f"{BASE_DIR}data_schema{os.sep}database_clean_server.db",
            f"{BASE_DIR}experiments{os.sep}dummy.db",
        )

    app = Flask(__name__)
    app.config["SECRET_KEY"] = "4YrzfpQ4kGXjuP6w"
    app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///../experiments/dummy.db"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False


    # db = SQLAlchemy()

    db.init_app(app)

    # Log the request duration
    @app.before_request
    def start_timer():
        g.start_time = time.time()


    @app.after_request
    def log_request(response):
        if hasattr(g, 'start_time'):
            from y_server.modals import Rounds
            from sqlalchemy import desc
            
            duration = time.time() - g.start_time
            log = {
                "remote_addr": request.remote_addr,
                "method": request.method,
                "path": request.path,
                "status_code": response.status_code,
                "duration": round(duration, 4),
                "time": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
            }
            
            # Add current round information from the database
            try:
                current_round = Rounds.query.order_by(desc(Rounds.id)).first()
                if current_round:
                    log["tid"] = current_round.id
                    log["day"] = current_round.day
                    log["hour"] = current_round.hour
            except:
                # If there's an error querying the database, continue without round info
                pass

            logging.info(log)
        return response

from y_server.routes import *
