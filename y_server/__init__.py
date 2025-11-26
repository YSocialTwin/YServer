import json
import logging
import os
import shutil
import time

from flask import Flask, g, request
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import desc
from sqlalchemy.pool import NullPool

log = logging.getLogger('werkzeug')
log.setLevel(logging.WARNING)
db = SQLAlchemy()

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
    
    # Set up JSON logging
    from pythonjsonlogger import jsonlogger
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    
    # Remove all existing handlers to avoid duplicate logging
    root_logger.handlers.clear()
    
    # Create file handler with JSON formatter
    formatter = jsonlogger.JsonFormatter()
    file_handler = logging.FileHandler(log_path, mode='a')
    file_handler.setFormatter(formatter)
    file_handler.setLevel(logging.INFO)
    root_logger.addHandler(file_handler)
    
    # Disable propagation to prevent logging to parent handlers
    root_logger.propagate = False
    
    # Ensure the log is flushed to disk
    file_handler.flush()
    
    # Log startup information
    logging.info("YServer started", extra={
        "database_uri": db_uri,
        "log_path": log_path,
        "config_file": config_file
    })
    
    # Clean up database sessions after each request
    # Essential when using NullPool to ensure connections are properly closed
    @app.teardown_appcontext
    def shutdown_session(exception=None):
        db.session.remove()

    # Teardown request handler to rollback uncommitted transactions on error
    # This ensures database access is safe and reliable by rolling back any
    # uncommitted transactions when an exception occurs during request handling
    @app.teardown_request
    def teardown_request_handler(exception=None):
        if exception is not None:
            # Rollback any uncommitted changes if an exception occurred
            try:
                db.session.rollback()
            except Exception:
                pass

    # Global error handler to catch all unhandled exceptions
    # This prevents the server from crashing and returns a proper error response
    @app.errorhandler(Exception)
    def handle_exception(e):
        # Rollback any failed transaction
        try:
            db.session.rollback()
        except Exception:
            pass
        
        # Log the error
        logging.error(f"Unhandled exception: {str(e)}", exc_info=True)
        
        # Return a JSON error response
        import json
        return json.dumps({"error": str(e), "status": 500}), 500

    # Log the request duration
    @app.before_request
    def start_timer():
        g.start_time = time.time()


    @app.after_request
    def log_request(response):
        if hasattr(g, 'start_time'):
            # Import here to avoid circular import (modals.py imports db from y_server)
            from y_server.modals import Rounds
            
            duration = time.time() - g.start_time
            log_data = {
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
                    log_data["tid"] = current_round.id
                    log_data["day"] = current_round.day
                    log_data["hour"] = current_round.hour
            except Exception:
                # If there's an error querying the database, continue without round info
                pass

            # Pass log data as extra dict so fields appear at top level in JSON output
            logging.info("request", extra=log_data)
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
    
    # Set up file logging to _server.log for Y Web subprocess
    log_dir = f"{BASE_DIR}experiments"
    log_path = os.path.join(log_dir, "_server.log")
    
    # Set up JSON logging
    from pythonjsonlogger import jsonlogger
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    
    # Remove all existing handlers to avoid duplicate logging
    root_logger.handlers.clear()
    
    # Create file handler with JSON formatter
    formatter = jsonlogger.JsonFormatter()
    file_handler = logging.FileHandler(log_path, mode='a')
    file_handler.setFormatter(formatter)
    file_handler.setLevel(logging.INFO)
    root_logger.addHandler(file_handler)
    
    # Disable propagation to prevent logging to parent handlers
    root_logger.propagate = False
    
    # Ensure the log is flushed to disk
    file_handler.flush()
    
    # Log startup information
    logging.info("YServer started (Y Web subprocess)", extra={
        "database_uri": app.config["SQLALCHEMY_DATABASE_URI"],
        "log_path": log_path
    })
    
    # Clean up database sessions after each request
    # Essential when using NullPool to ensure connections are properly closed
    @app.teardown_appcontext
    def shutdown_session(exception=None):
        db.session.remove()

    # Teardown request handler to rollback uncommitted transactions on error
    # This ensures database access is safe and reliable by rolling back any
    # uncommitted transactions when an exception occurs during request handling
    @app.teardown_request
    def teardown_request_handler(exception=None):
        if exception is not None:
            # Rollback any uncommitted changes if an exception occurred
            try:
                db.session.rollback()
            except Exception:
                pass

    # Global error handler to catch all unhandled exceptions
    # This prevents the server from crashing and returns a proper error response
    @app.errorhandler(Exception)
    def handle_exception(e):
        # Rollback any failed transaction
        try:
            db.session.rollback()
        except Exception:
            pass
        
        # Log the error
        logging.error(f"Unhandled exception: {str(e)}", exc_info=True)
        
        # Return a JSON error response
        import json
        return json.dumps({"error": str(e), "status": 500}), 500

    # Log the request duration
    @app.before_request
    def start_timer():
        g.start_time = time.time()


    @app.after_request
    def log_request(response):
        if hasattr(g, 'start_time'):
            # Import here to avoid circular import (modals.py imports db from y_server)
            from y_server.modals import Rounds
            
            duration = time.time() - g.start_time
            log_data = {
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
                    log_data["tid"] = current_round.id
                    log_data["day"] = current_round.day
                    log_data["hour"] = current_round.hour
            except Exception:
                # If there's an error querying the database, continue without round info
                pass

            # Pass log data as extra dict so fields appear at top level in JSON output
            logging.info("request", extra=log_data)
        return response

from y_server.routes import *
