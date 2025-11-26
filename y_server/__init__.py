import json
import logging
import os
import shutil
import time
import threading

from flask import Flask, g, request
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import desc
from sqlalchemy.pool import NullPool

log = logging.getLogger('werkzeug')
log.setLevel(logging.WARNING)
db = SQLAlchemy()

# Track active requests for debugging hangs
_active_requests = {}
_request_lock = threading.Lock()

try:
    # read the experiment configuration
    # Support YSERVER_CONFIG environment variable to allow custom config paths
    config_file = os.environ.get('YSERVER_CONFIG', f"config_files{os.sep}exp_config.json")
    config = json.load(open(config_file))

    # create the experiments folder
    if not os.path.exists(f".{os.sep}experiments"):
        os.mkdir(f".{os.sep}experiments")

    # Determine database URI
    # Priority: 1) database_uri from config, 2) default SQLite based on name
    if "database_uri" in config and config["database_uri"]:
        db_uri = config["database_uri"]
        # For SQLite URIs, ensure the database file exists
        if db_uri.startswith("sqlite"):
            # Extract path from sqlite:/// URI
            db_path = db_uri.replace("sqlite:///", "").replace("sqlite://", "")
            if not os.path.exists(db_path) or config.get("reset_db") == "True":
                # Create directory if needed
                db_dir = os.path.dirname(db_path)
                if db_dir and not os.path.exists(db_dir):
                    os.makedirs(db_dir, exist_ok=True)
                # Copy clean database
                shutil.copyfile(
                    f"data_schema{os.sep}database_clean_server.db",
                    db_path,
                )
    else:
        # Default: use name-based SQLite database
        db_path = f"experiments{os.sep}{config['name']}.db"
        if (
            not os.path.exists(db_path)
            or config.get("reset_db") == "True"
        ):
            # copy the clean database to the experiments folder
            shutil.copyfile(
                f"data_schema{os.sep}database_clean_server.db",
                db_path,
            )
        db_uri = f"sqlite:///../experiments/{config['name']}.db"

    app = Flask(__name__)
    app.config["SECRET_KEY"] = "4YrzfpQ4kGXjuP6w"
    app.config["SQLALCHEMY_DATABASE_URI"] = db_uri
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    
    # Configure engine options based on database type
    # Use NullPool for both SQLite and PostgreSQL for Gunicorn compatibility
    # NullPool ensures each request gets a fresh connection, avoiding connection pool issues
    # with multiple gunicorn workers
    if db_uri.startswith("sqlite"):
        # SQLite-specific configuration
        app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
            "poolclass": NullPool,
            "connect_args": {
                "check_same_thread": False,
                "timeout": 30  # Increase timeout for busy databases
            }
        }
    else:
        # PostgreSQL and other databases: use NullPool to avoid connection pool issues
        # with multiple gunicorn workers (each worker would maintain its own pool)
        app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
            "poolclass": NullPool,
        }
    
    db = SQLAlchemy(app)

    # Set up file logging to _server.log
    # Determine log directory based on database URI
    if db_uri.startswith("sqlite"):
        # Extract path from sqlite URI and get directory
        db_path = db_uri.replace("sqlite:///", "").replace("sqlite://", "")
        # Remove leading slashes for relative paths
        if db_path.startswith("../"):
            db_path = db_path[3:]
        log_dir = os.path.dirname(db_path) if os.path.dirname(db_path) else "experiments"
    else:
        # For PostgreSQL or other databases, use a default log location
        base = os.getcwd().split("external")[0]
        uiid = config["database_uri"].split("experiments_")[1]
        log_dir = f"{base}{os.sep}y_web{os.sep}experiments{os.sep}{uiid}"


    log_path = os.path.join(log_dir, "_server.log")
    
    # Create log directory if it doesn't exist
    os.makedirs(log_dir, exist_ok=True)
    
    # Set up JSON logging with rotation to prevent log file from growing indefinitely
    # Large log files can cause I/O blocking and contribute to performance issues
    from pythonjsonlogger import jsonlogger
    from logging.handlers import RotatingFileHandler
    
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)  # Set to DEBUG for more detailed logging
    
    # Remove all existing handlers to avoid duplicate logging
    root_logger.handlers.clear()
    
    # Create rotating file handler with JSON formatter
    # Max 10MB per file, keep 5 backup files (total max ~60MB of logs)
    formatter = jsonlogger.JsonFormatter()
    file_handler = RotatingFileHandler(
        log_path, 
        mode='a', 
        maxBytes=10*1024*1024,  # 10MB
        backupCount=5
    )
    file_handler.setFormatter(formatter)
    file_handler.setLevel(logging.DEBUG)  # Set to DEBUG for more detailed logging
    root_logger.addHandler(file_handler)
    
    # Disable propagation to prevent logging to parent handlers
    root_logger.propagate = False
    
    # Ensure the log is flushed to disk
    file_handler.flush()
    
    # Log startup information
    logging.info("YServer started", extra={
        "database_uri": db_uri,
        "log_path": log_path,
        "config_file": config_file,
        "pid": os.getpid(),
        "thread_id": threading.current_thread().ident
    })
    
    # Clean up database sessions after each request
    # Essential when using NullPool to ensure connections are properly closed
    @app.teardown_appcontext
    def shutdown_session(exception=None):
        if exception:
            logging.warning("teardown_appcontext with exception", extra={
                "exception": str(exception),
                "path": request.path if request else "unknown"
            })
        db.session.remove()

    # Enhanced before_request logging to track active requests
    @app.before_request
    def start_timer():
        g.start_time = time.time()
        g.request_id = f"{time.time()}-{threading.current_thread().ident}"
        
        # Track this request
        with _request_lock:
            _active_requests[g.request_id] = {
                "path": request.path,
                "method": request.method,
                "start_time": g.start_time,
                "thread_id": threading.current_thread().ident
            }
        
        # Log request start with detailed info
        logging.debug("request_start", extra={
            "request_id": g.request_id,
            "path": request.path,
            "method": request.method,
            "thread_id": threading.current_thread().ident,
            "active_requests": len(_active_requests),
            "content_length": request.content_length
        })

    @app.after_request
    def log_request(response):
        if hasattr(g, 'start_time'):
            # Import here to avoid circular import (modals.py imports db from y_server)
            from y_server.modals import Rounds
            
            duration = time.time() - g.start_time
            
            # Remove from active requests tracking
            request_id = getattr(g, 'request_id', None)
            if request_id:
                with _request_lock:
                    _active_requests.pop(request_id, None)
            
            log_data = {
                "request_id": request_id,
                "remote_addr": request.remote_addr,
                "method": request.method,
                "path": request.path,
                "status_code": response.status_code,
                "duration": round(duration, 4),
                "time": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime()),
                "thread_id": threading.current_thread().ident,
                "active_requests_remaining": len(_active_requests)
            }
            
            # Warn if request took too long
            if duration > 5.0:
                logging.warning("slow_request", extra=log_data)
            
            # Add current round information from the database
            try:
                current_round = Rounds.query.order_by(desc(Rounds.id)).first()
                if current_round:
                    log_data["tid"] = current_round.id
                    log_data["day"] = current_round.day
                    log_data["hour"] = current_round.hour
            except Exception as e:
                # If there's an error querying the database, log it
                log_data["db_query_error"] = str(e)
                logging.warning("db_query_failed_in_after_request", extra={"error": str(e)})

            # Pass log data as extra dict so fields appear at top level in JSON output
            logging.info("request_complete", extra=log_data)
        return response
    
    # Add endpoint to check active requests (for debugging hangs)
    @app.route("/debug/active_requests", methods=["GET"])
    def debug_active_requests():
        """Return list of currently active requests for debugging hangs."""
        with _request_lock:
            active = []
            current_time = time.time()
            for req_id, req_info in _active_requests.items():
                active.append({
                    "request_id": req_id,
                    "path": req_info["path"],
                    "method": req_info["method"],
                    "duration_so_far": round(current_time - req_info["start_time"], 2),
                    "thread_id": req_info["thread_id"]
                })
            return json.dumps({
                "active_request_count": len(active),
                "requests": active,
                "server_pid": os.getpid()
            })

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
    
    # SQLite-specific configuration for Gunicorn compatibility
    # Use NullPool to disable connection pooling (SQLite doesn't handle pooling well)
    app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
        "poolclass": NullPool,
        "connect_args": {
            "check_same_thread": False,
            "timeout": 30  # Increase timeout for busy databases
        }
    }

    # db = SQLAlchemy()

    db.init_app(app)
    
    # Set up file logging to _server.log for Y Web subprocess with rotation
    # Large log files can cause I/O blocking and contribute to performance issues
    log_dir = f"{BASE_DIR}experiments"
    log_path = os.path.join(log_dir, "_server.log")
    
    # Set up JSON logging with rotation
    from pythonjsonlogger import jsonlogger
    from logging.handlers import RotatingFileHandler
    
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)  # Set to DEBUG for more detailed logging
    
    # Remove all existing handlers to avoid duplicate logging
    root_logger.handlers.clear()
    
    # Create rotating file handler with JSON formatter
    # Max 10MB per file, keep 5 backup files (total max ~60MB of logs)
    formatter = jsonlogger.JsonFormatter()
    file_handler = RotatingFileHandler(
        log_path, 
        mode='a', 
        maxBytes=10*1024*1024,  # 10MB
        backupCount=5
    )
    file_handler.setFormatter(formatter)
    file_handler.setLevel(logging.DEBUG)  # Set to DEBUG for more detailed logging
    root_logger.addHandler(file_handler)
    
    # Disable propagation to prevent logging to parent handlers
    root_logger.propagate = False
    
    # Ensure the log is flushed to disk
    file_handler.flush()
    
    # Log startup information
    logging.info("YServer started (Y Web subprocess)", extra={
        "database_uri": app.config["SQLALCHEMY_DATABASE_URI"],
        "log_path": log_path,
        "pid": os.getpid(),
        "thread_id": threading.current_thread().ident
    })
    
    # Clean up database sessions after each request
    # Essential when using NullPool to ensure connections are properly closed
    @app.teardown_appcontext
    def shutdown_session(exception=None):
        if exception:
            logging.warning("teardown_appcontext with exception", extra={
                "exception": str(exception),
                "path": request.path if request else "unknown"
            })
        db.session.remove()

    # Enhanced before_request logging to track active requests
    @app.before_request
    def start_timer():
        g.start_time = time.time()
        g.request_id = f"{time.time()}-{threading.current_thread().ident}"
        
        # Track this request
        with _request_lock:
            _active_requests[g.request_id] = {
                "path": request.path,
                "method": request.method,
                "start_time": g.start_time,
                "thread_id": threading.current_thread().ident
            }
        
        # Log request start with detailed info
        logging.debug("request_start", extra={
            "request_id": g.request_id,
            "path": request.path,
            "method": request.method,
            "thread_id": threading.current_thread().ident,
            "active_requests": len(_active_requests),
            "content_length": request.content_length
        })

    @app.after_request
    def log_request(response):
        if hasattr(g, 'start_time'):
            # Import here to avoid circular import (modals.py imports db from y_server)
            from y_server.modals import Rounds
            
            duration = time.time() - g.start_time
            
            # Remove from active requests tracking
            request_id = getattr(g, 'request_id', None)
            if request_id:
                with _request_lock:
                    _active_requests.pop(request_id, None)
            
            log_data = {
                "request_id": request_id,
                "remote_addr": request.remote_addr,
                "method": request.method,
                "path": request.path,
                "status_code": response.status_code,
                "duration": round(duration, 4),
                "time": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime()),
                "thread_id": threading.current_thread().ident,
                "active_requests_remaining": len(_active_requests)
            }
            
            # Warn if request took too long
            if duration > 5.0:
                logging.warning("slow_request", extra=log_data)
            
            # Add current round information from the database
            try:
                current_round = Rounds.query.order_by(desc(Rounds.id)).first()
                if current_round:
                    log_data["tid"] = current_round.id
                    log_data["day"] = current_round.day
                    log_data["hour"] = current_round.hour
            except Exception as e:
                # If there's an error querying the database, log it
                log_data["db_query_error"] = str(e)
                logging.warning("db_query_failed_in_after_request", extra={"error": str(e)})

            # Pass log data as extra dict so fields appear at top level in JSON output
            logging.info("request_complete", extra=log_data)
        return response
    
    # Add endpoint to check active requests (for debugging hangs)
    @app.route("/debug/active_requests", methods=["GET"])
    def debug_active_requests():
        """Return list of currently active requests for debugging hangs."""
        with _request_lock:
            active = []
            current_time = time.time()
            for req_id, req_info in _active_requests.items():
                active.append({
                    "request_id": req_id,
                    "path": req_info["path"],
                    "method": req_info["method"],
                    "duration_so_far": round(current_time - req_info["start_time"], 2),
                    "thread_id": req_info["thread_id"]
                })
            return json.dumps({
                "active_request_count": len(active),
                "requests": active,
                "server_pid": os.getpid()
            })

from y_server.routes import *
