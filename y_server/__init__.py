import atexit
import json
import logging
import os
import shutil
import signal
import sys
import time
import threading
import traceback
from datetime import datetime

from flask import Flask, g, request
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import desc, text, inspect
from sqlalchemy.pool import NullPool


def _log_error_stderr(message):
    """
    Log an error message to stderr with timestamp formatting.
    
    Each write starts with "### date and time ###\n" and ends with "\n####".
    Uses flush=True to ensure immediate output for debugging.
    
    :param message: the error message to log
    """
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"### {timestamp} ###\n{message}\n####", file=sys.stderr, flush=True)


# Store the original sys.exit for our wrapper
_original_sys_exit = sys.exit


def _wrapped_sys_exit(code=0):
    """
    Wrapper around sys.exit to log who is calling it.
    This helps identify what's causing normal process termination.
    """
    stack_trace = ''.join(traceback.format_stack())
    _log_error_stderr(f"SYS.EXIT CALLED with code={code}\nProcess ID: {os.getpid()}\nThread ID: {threading.current_thread().ident}\nCaller stack trace:\n{stack_trace}")
    _original_sys_exit(code)


# Replace sys.exit with our wrapper
sys.exit = _wrapped_sys_exit


def _signal_handler(signum, frame):
    """
    Handle termination signals and log before exit.
    This helps identify why the process is dying unexpectedly.
    """
    signal_name = signal.Signals(signum).name if hasattr(signal, 'Signals') else str(signum)
    _log_error_stderr(f"SIGNAL RECEIVED: {signal_name} (signal {signum})\nProcess ID: {os.getpid()}\nThread ID: {threading.current_thread().ident}\nStack trace:\n{''.join(traceback.format_stack(frame))}")
    # Re-raise the signal to allow normal termination after logging
    signal.signal(signum, signal.SIG_DFL)
    os.kill(os.getpid(), signum)


def _atexit_handler():
    """
    Log when the process is exiting.
    This helps identify unexpected termination.
    Note: By the time atexit runs, the original call stack is gone.
    Use the sys.exit wrapper to capture exit calls with their stack traces.
    """
    _log_error_stderr(f"PROCESS EXITING: atexit handler called\nProcess ID: {os.getpid()}\nThread ID: {threading.current_thread().ident}\nNote: If no SYS.EXIT CALLED log appeared before this, the exit was triggered by main thread completion or os._exit()")


def _uncaught_exception_handler(exc_type, exc_value, exc_traceback):
    """
    Handle uncaught exceptions and log them before the process exits.
    This catches exceptions that would otherwise cause silent termination.
    """
    if issubclass(exc_type, KeyboardInterrupt):
        # Call the default handler for keyboard interrupt
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
        return
    
    tb_lines = traceback.format_exception(exc_type, exc_value, exc_traceback)
    _log_error_stderr(f"UNCAUGHT EXCEPTION: {exc_type.__name__}: {exc_value}\nProcess ID: {os.getpid()}\nThread ID: {threading.current_thread().ident}\nFull traceback:\n{''.join(tb_lines)}")
    # Call the default handler
    sys.__excepthook__(exc_type, exc_value, exc_traceback)


def _uncaught_thread_exception_handler(args):
    """
    Handle uncaught exceptions in threads.
    Python 3.8+ threading.excepthook handler.
    """
    tb_lines = traceback.format_exception(args.exc_type, args.exc_value, args.exc_traceback)
    _log_error_stderr(f"UNCAUGHT THREAD EXCEPTION in thread '{args.thread.name}': {args.exc_type.__name__}: {args.exc_value}\nProcess ID: {os.getpid()}\nThread ID: {args.thread.ident}\nFull traceback:\n{''.join(tb_lines)}")


# Register atexit handler to log process exit
atexit.register(_atexit_handler)

# Register global exception hook for uncaught exceptions
sys.excepthook = _uncaught_exception_handler

# Register thread exception hook (Python 3.8+)
if hasattr(threading, 'excepthook'):
    threading.excepthook = _uncaught_thread_exception_handler

# Register signal handlers for common termination signals
# Note: SIGKILL (9) cannot be caught
try:
    signal.signal(signal.SIGTERM, _signal_handler)  # Termination signal
    signal.signal(signal.SIGINT, _signal_handler)   # Interrupt (Ctrl+C)
    if hasattr(signal, 'SIGHUP'):
        signal.signal(signal.SIGHUP, _signal_handler)  # Hangup signal (Unix only)
    if hasattr(signal, 'SIGQUIT'):
        signal.signal(signal.SIGQUIT, _signal_handler)  # Quit signal (Unix only)
except Exception as e:
    _log_error_stderr(f"Failed to register signal handlers: {str(e)}")


log = logging.getLogger('werkzeug')
log.setLevel(logging.WARNING)
db = SQLAlchemy()


def _migrate_database_schema(db_instance, mode="main"):
    """
    Check and add missing columns to database tables.
    This ensures backward compatibility when new columns are added to models.
    
    :param db_instance: SQLAlchemy database instance
    :param mode: "main" or "subprocess" for logging context
    """
    try:
        # Check if archetype column exists in user_mgmt table
        inspector = inspect(db_instance.engine)
        columns = [col['name'] for col in inspector.get_columns('user_mgmt')]
        
        if 'archetype' not in columns:
            # Add the archetype column with default value
            with db_instance.engine.begin() as conn:
                conn.execute(text('ALTER TABLE user_mgmt ADD COLUMN archetype TEXT DEFAULT NULL'))
            log_msg = "Database migration: Added archetype column to user_mgmt table"
            if mode == "subprocess":
                log_msg = "Database migration (subprocess): Added archetype column to user_mgmt table"
            logging.info(log_msg)
    except Exception as e:
        error_msg = f"Database migration error ({mode}): {str(e)}"
        logging.error(error_msg)
        _log_error_stderr(f"{error_msg}\nTraceback: {traceback.format_exc()}")


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

    # Run migration after database is initialized
    with app.app_context():
        _migrate_database_schema(db, mode="main")

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
            _log_error_stderr(f"teardown_appcontext exception: {str(exception)}\nPath: {request.path if request else 'unknown'}\nTraceback: {traceback.format_exc()}")
            logging.warning("teardown_appcontext with exception", extra={
                "exception": str(exception),
                "path": request.path if request else "unknown"
            })
        try:
            db.session.remove()
        except Exception as e:
            _log_error_stderr(f"teardown_appcontext: CRITICAL ERROR removing session\nError: {str(e)}\nPath: {request.path if request else 'unknown'}\nTraceback: {traceback.format_exc()}")

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
            
            # Warn if request took too long (main process)
            if duration > 5.0:
                _log_error_stderr(f"slow_request detected (main): {request.path} took {duration:.4f}s")
                logging.warning("slow_request", extra=log_data)
            
            # Add current round information from the database (main process)
            try:
                current_round = Rounds.query.order_by(desc(Rounds.id)).first()
                if current_round:
                    log_data["tid"] = current_round.id
                    log_data["day"] = current_round.day
                    log_data["hour"] = current_round.hour
            except Exception as e:
                # If there's an error querying the database, log it (main process)
                _log_error_stderr(f"db_query_failed_in_after_request (main): {str(e)}\nPath: {request.path}\nTraceback: {traceback.format_exc()}")
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

except Exception as init_exception:  # Y Web subprocess
    # Log initialization error to stderr
    _log_error_stderr(f"YServer initialization error (falling back to Y Web subprocess mode): {str(init_exception)}\nTraceback: {traceback.format_exc()}")
    
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
    
    # Run migration after database is initialized
    with app.app_context():
        _migrate_database_schema(db, mode="subprocess")
    
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
            _log_error_stderr(f"teardown_appcontext exception (subprocess): {str(exception)}\nPath: {request.path if request else 'unknown'}\nTraceback: {traceback.format_exc()}")
            logging.warning("teardown_appcontext with exception", extra={
                "exception": str(exception),
                "path": request.path if request else "unknown"
            })
        try:
            db.session.remove()
        except Exception as e:
            _log_error_stderr(f"teardown_appcontext (subprocess): CRITICAL ERROR removing session\nError: {str(e)}\nPath: {request.path if request else 'unknown'}\nTraceback: {traceback.format_exc()}")

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
            
            # Warn if request took too long (Y Web subprocess)
            if duration > 5.0:
                _log_error_stderr(f"slow_request detected (subprocess): {request.path} took {duration:.4f}s")
                logging.warning("slow_request", extra=log_data)
            
            # Add current round information from the database (Y Web subprocess)
            try:
                current_round = Rounds.query.order_by(desc(Rounds.id)).first()
                if current_round:
                    log_data["tid"] = current_round.id
                    log_data["day"] = current_round.day
                    log_data["hour"] = current_round.hour
            except Exception as e:
                # If there's an error querying the database, log it (Y Web subprocess)
                _log_error_stderr(f"db_query_failed_in_after_request (subprocess): {str(e)}\nPath: {request.path}\nTraceback: {traceback.format_exc()}")
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
