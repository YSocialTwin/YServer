from flask import Flask, g, request
from flask_sqlalchemy import SQLAlchemy
import json
import shutil
import os
import time
from datetime import datetime


def _ensure_optional_analytics_schema():
    """
    Create additive analytics/opinion tables for legacy experiment DBs.

    Existing installations are based on prebuilt SQLite files, so these tables
    may be missing even though newer client logic expects them to exist.
    """
    try:
        with app.app_context():
            from y_server.modals import Agent_Opinion, Post_Sentiment, Post_Toxicity

            Agent_Opinion.__table__.create(bind=db.engine, checkfirst=True)
            Post_Sentiment.__table__.create(bind=db.engine, checkfirst=True)
            Post_Toxicity.__table__.create(bind=db.engine, checkfirst=True)
    except Exception:
        pass

try:
    # read the experiment configuration
    config = json.load(
        open(os.environ.get("YSERVER_CONFIG", f"config_files{os.sep}exp_config.json"))
    )

    # create the experiments folder
    if not os.path.exists(f".{os.sep}experiments"):
        os.mkdir(f".{os.sep}experiments")


    if (
        not os.path.exists(f"experiments{os.sep}{config['name']}.db")
        or config["reset_db"] == "True"
    ):
        # copy the clean database to the experiments folder
        shutil.copyfile(
            f"data_schema{os.sep}database_clean_server.db", f"experiments{os.sep}{config['name']}.db"
        )

    app = Flask(__name__)
    app.config["SECRET_KEY"] = "4YrzfpQ4kGXjuP6w"
    app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///../experiments/{config['name']}.db"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    db = SQLAlchemy(app)

except: # Y Web subprocess
    # base path
    BASE_DIR = os.path.dirname(os.path.abspath(__file__)).split("y_server")[0]

    # create the experiments folder
    if not os.path.exists(f"{BASE_DIR}experiments"):
        os.mkdir(f"{BASE_DIR}experiments")
        shutil.copyfile(
            f"{BASE_DIR}data_schema{os.sep}database_clean_server.db", f"{BASE_DIR}experiments{os.sep}dummy.db"
        )

    app = Flask(__name__)
    app.config["SECRET_KEY"] = "4YrzfpQ4kGXjuP6w"
    app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///../experiments/dummy.db"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    db = SQLAlchemy(app)


def _server_log_path():
    configured = str(app.config.get("log_file", "") or "").strip()
    if configured:
        return configured
    return str(os.environ.get("YSERVER_LOG_FILE", "") or "").strip()


def _append_server_log(payload):
    path = _server_log_path()
    if not path:
        return
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
    except Exception:
        return
    try:
        with open(path, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=True) + "\n")
    except Exception:
        return


def _resolve_round_context():
    day = None
    hour = None
    tid = None
    try:
        raw = request.get_data(cache=True, as_text=True) or ""
        payload = json.loads(raw) if raw.strip() else {}
    except Exception:
        payload = {}
    if isinstance(payload, dict):
        try:
            tid = int(payload.get("tid")) if payload.get("tid") is not None else None
        except Exception:
            tid = None
        if tid is None:
            try:
                tid = int(payload.get("round")) if payload.get("round") is not None else None
            except Exception:
                tid = None
    try:
        from y_server.modals import Rounds

        if tid is not None:
            row = Rounds.query.filter_by(id=int(tid)).first()
            if row is not None:
                return int(row.day), int(row.hour)
        latest = Rounds.query.order_by(Rounds.id.desc()).first()
        if latest is not None:
            day = int(latest.day)
            hour = int(latest.hour)
    except Exception:
        pass
    return day, hour


@app.before_request
def _ysocial_before_request():
    g._ysocial_started_at = time.perf_counter()


@app.after_request
def _ysocial_after_request(response):
    try:
        started = float(getattr(g, "_ysocial_started_at", time.perf_counter()))
        duration = max(0.0, time.perf_counter() - started)
        day, hour = _resolve_round_context()
        payload = {
            "time": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
            "path": request.path,
            "status_code": int(getattr(response, "status_code", 0) or 0),
            "duration": round(duration, 6),
            "day": day,
            "hour": hour,
            "method": request.method,
        }
        _append_server_log(payload)
    except Exception:
        pass
    return response

from y_server.routes import *

_ensure_optional_analytics_schema()
