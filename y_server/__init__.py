"""
YSocial Server initialization module.

This module initializes the Flask application and SQLAlchemy database connection for
the YSocial microblogging digital twin platform. It handles configuration loading,
database setup, and request logging middleware.

The module supports two modes:
    1. Experiment mode: Uses configuration from config_files/exp_config.json
    2. Y Web subprocess mode: Falls back to a dummy database configuration

Attributes:
    app: Flask application instance
    db: SQLAlchemy database instance
    logger: Werkzeug logger instance
"""

from flask import Flask, request, g
from flask_sqlalchemy import SQLAlchemy
import json
import shutil
import os
import logging, time

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
        """Record the start time of each request for duration logging."""
        g.start_time = time.time()


    @app.after_request
    def log_request(response):
        """
        Log request information after each request is processed.
        
        Logs the remote address, HTTP method, path, status code, duration,
        and timestamp for each request.
        
        Args:
            response: Flask response object
            
        Returns:
            Flask response object (unchanged)
        """
        if hasattr(g, 'start_time'):
            duration = time.time() - g.start_time
            log = {
                "remote_addr": request.remote_addr,
                "method": request.method,
                "path": request.path,
                "status_code": response.status_code,
                "duration": round(duration, 4),
                "time": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
            }

            logging.info(log)
        return response

from y_server.routes import *
