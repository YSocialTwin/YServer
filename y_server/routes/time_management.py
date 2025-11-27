import json
import logging
import time as pytime
import threading
import traceback
from functools import wraps

from flask import request
from sqlalchemy import desc
from sqlalchemy.exc import OperationalError
from y_server import app, db
from y_server.error_logging import log_error
from y_server.modals import (
    Rounds,
)


def force_release_sqlite_lock():
    """
    Force release SQLite database lock by closing all connections and disposing the engine.
    This is a last resort when retries fail and the database remains locked.
    """
    try:
        log_error(f"force_release_sqlite_lock: Starting force release\nThread ID: {threading.current_thread().ident}")
        logging.warning("force_release_sqlite_lock: Starting force release", extra={
            "thread_id": threading.current_thread().ident
        })
        # Remove the current session
        db.session.remove()
        # Dispose the engine to close all connections in the pool
        db.engine.dispose()
        logging.warning("force_release_sqlite_lock: Successfully released lock", extra={
            "thread_id": threading.current_thread().ident
        })
        return True
    except Exception as e:
        log_error(f"force_release_sqlite_lock: Failed - {str(e)}\nThread ID: {threading.current_thread().ident}\nTraceback: {traceback.format_exc()}")
        logging.error(f"force_release_sqlite_lock: Failed - {str(e)}", extra={
            "thread_id": threading.current_thread().ident,
            "error": str(e)
        })
        return False


def retry_on_db_lock(max_retries=3, delay=0.5, force_release_on_failure=True):
    """
    Decorator to retry database operations when SQLite database is locked.
    This handles the "database is locked" error by waiting and retrying.
    If all retries fail and force_release_on_failure is True, it will force
    release the lock by disposing all connections and retry once more.
    
    :param max_retries: Maximum number of retry attempts
    :param delay: Delay between retries in seconds
    :param force_release_on_failure: If True, force release lock after all retries fail
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None
            func_name = func.__name__
            thread_id = threading.current_thread().ident
            
            for attempt in range(max_retries + 1):
                try:
                    if attempt > 0:
                        logging.debug(f"retry_on_db_lock: Attempt {attempt + 1} for {func_name}", extra={
                            "function": func_name,
                            "attempt": attempt + 1,
                            "thread_id": thread_id
                        })
                    return func(*args, **kwargs)
                except OperationalError as e:
                    if "database is locked" in str(e).lower():
                        last_exception = e
                        log_error(f"retry_on_db_lock: Database locked on attempt {attempt + 1}\nFunction: {func_name}\nThread ID: {thread_id}\nError: {str(e)}")
                        logging.warning(f"retry_on_db_lock: Database locked on attempt {attempt + 1}", extra={
                            "function": func_name,
                            "attempt": attempt + 1,
                            "max_retries": max_retries,
                            "thread_id": thread_id,
                            "error": str(e)
                        })
                        if attempt < max_retries:
                            # Rollback the failed transaction
                            try:
                                db.session.rollback()
                            except Exception as rollback_e:
                                log_error(f"retry_on_db_lock: Rollback failed - {str(rollback_e)}\nFunction: {func_name}")
                                logging.warning(f"retry_on_db_lock: Rollback failed - {str(rollback_e)}")
                            # Wait before retrying with exponential backoff
                            sleep_time = delay * (attempt + 1)
                            logging.debug(f"retry_on_db_lock: Sleeping {sleep_time}s before retry")
                            pytime.sleep(sleep_time)
                            continue
                    else:
                        log_error(f"retry_on_db_lock: Non-lock OperationalError\nFunction: {func_name}\nThread ID: {thread_id}\nError: {str(e)}\nTraceback: {traceback.format_exc()}")
                        logging.error(f"retry_on_db_lock: Non-lock OperationalError", extra={
                            "function": func_name,
                            "thread_id": thread_id,
                            "error": str(e)
                        })
                        raise
                except Exception as e:
                    log_error(f"retry_on_db_lock: Unexpected exception\nFunction: {func_name}\nThread ID: {thread_id}\nError Type: {type(e).__name__}\nError: {str(e)}\nTraceback: {traceback.format_exc()}")
                    logging.error(f"retry_on_db_lock: Unexpected exception", extra={
                        "function": func_name,
                        "thread_id": thread_id,
                        "error": str(e),
                        "error_type": type(e).__name__
                    })
                    raise
            
            # If we've exhausted all retries and still have a lock error
            if last_exception and force_release_on_failure:
                log_error(f"retry_on_db_lock: All {max_retries} retries exhausted, attempting force release\nFunction: {func_name}\nThread ID: {thread_id}")
                logging.warning(f"retry_on_db_lock: All {max_retries} retries exhausted, attempting force release", extra={
                    "function": func_name,
                    "thread_id": thread_id
                })
                # Force release the lock
                if force_release_sqlite_lock():
                    # Wait a moment for the lock to be fully released
                    pytime.sleep(0.5)
                    # Try one final time after force release
                    try:
                        logging.info(f"retry_on_db_lock: Final attempt after force release", extra={
                            "function": func_name,
                            "thread_id": thread_id
                        })
                        return func(*args, **kwargs)
                    except Exception as final_e:
                        log_error(f"retry_on_db_lock: Failed even after force release\nFunction: {func_name}\nThread ID: {thread_id}\nError: {str(final_e)}\nTraceback: {traceback.format_exc()}")
                        logging.error(f"retry_on_db_lock: Failed even after force release", extra={
                            "function": func_name,
                            "thread_id": thread_id,
                            "error": str(final_e)
                        })
                        raise final_e
            
            # If we've exhausted all retries, raise the last exception
            if last_exception:
                log_error(f"retry_on_db_lock: Giving up after all retries\nFunction: {func_name}\nThread ID: {thread_id}\nError: {str(last_exception)}")
                logging.error(f"retry_on_db_lock: Giving up after all retries", extra={
                    "function": func_name,
                    "thread_id": thread_id,
                    "error": str(last_exception)
                })
                raise last_exception
        return wrapper
    return decorator


@app.route("/current_time", methods=["GET"])
def current_time():
    """
    Get the current time of the simulation.

    :return: a json object with the current time
    """
    start_time = pytime.time()
    thread_id = threading.current_thread().ident
    
    logging.debug("current_time: Handler started", extra={
        "thread_id": thread_id
    })
    
    @retry_on_db_lock(max_retries=3, delay=0.5, force_release_on_failure=True)
    def _get_current_time():
        logging.debug("current_time: Querying database", extra={
            "thread_id": thread_id
        })
        cround = Rounds.query.order_by(desc(Rounds.id)).first()
        if cround is None:
            logging.debug("current_time: No round found, creating new", extra={
                "thread_id": thread_id
            })
            cround = Rounds(day=0, hour=0)
            db.session.add(cround)
            db.session.commit()
            cround = Rounds.query.order_by(desc(Rounds.id)).first()
        return cround

    try:
        cround = _get_current_time()
        duration = pytime.time() - start_time
        logging.debug("current_time: Success", extra={
            "thread_id": thread_id,
            "duration": round(duration, 4),
            "round_id": cround.id
        })
        return json.dumps({"id": cround.id, "day": cround.day, "round": cround.hour})
    except Exception as e:
        duration = pytime.time() - start_time
        log_error(f"current_time: Failed\nThread ID: {thread_id}\nDuration: {duration:.4f}s\nError Type: {type(e).__name__}\nError: {str(e)}\nTraceback: {traceback.format_exc()}")
        logging.error("current_time: Failed", extra={
            "thread_id": thread_id,
            "duration": round(duration, 4),
            "error": str(e),
            "error_type": type(e).__name__
        })
        # Rollback any failed transaction
        try:
            db.session.rollback()
        except Exception as rollback_e:
            log_error(f"current_time: Rollback failed - {str(rollback_e)}")
            logging.warning(f"current_time: Rollback failed - {str(rollback_e)}")
        return json.dumps({"error": str(e), "status": 500}), 500


@app.route("/update_time", methods=["POST"])
def update_time():
    """
    Update the time of the simulation.

    :return: a json object with the updated time
    """
    start_time = pytime.time()
    thread_id = threading.current_thread().ident
    
    logging.debug("update_time: Handler started", extra={
        "thread_id": thread_id
    })
    
    @retry_on_db_lock(max_retries=3, delay=0.5, force_release_on_failure=True)
    def _update_time(day, hour):
        logging.debug("update_time: Querying database", extra={
            "thread_id": thread_id,
            "day": day,
            "hour": hour
        })
        cround = Rounds.query.filter_by(day=day, hour=hour).first()
        if cround is None:
            logging.debug("update_time: Creating new round", extra={
                "thread_id": thread_id,
                "day": day,
                "hour": hour
            })
            cround = Rounds(day=day, hour=hour)
            db.session.add(cround)
            db.session.commit()
            cround = Rounds.query.filter_by(day=day, hour=hour).first()
        return cround

    try:
        data = json.loads(request.get_data())
        day = int(data["day"])
        hour = int(data["round"])

        cround = _update_time(day, hour)
        duration = pytime.time() - start_time
        logging.debug("update_time: Success", extra={
            "thread_id": thread_id,
            "duration": round(duration, 4),
            "round_id": cround.id
        })
        return json.dumps({"id": cround.id, "day": cround.day, "round": cround.hour})
    except Exception as e:
        duration = pytime.time() - start_time
        log_error(f"update_time: Failed\nThread ID: {thread_id}\nDuration: {duration:.4f}s\nError Type: {type(e).__name__}\nError: {str(e)}\nTraceback: {traceback.format_exc()}")
        logging.error("update_time: Failed", extra={
            "thread_id": thread_id,
            "duration": round(duration, 4),
            "error": str(e),
            "error_type": type(e).__name__
        })
        # Rollback any failed transaction
        try:
            db.session.rollback()
        except Exception as rollback_e:
            log_error(f"update_time: Rollback failed - {str(rollback_e)}")
            logging.warning(f"update_time: Rollback failed - {str(rollback_e)}")
        return json.dumps({"error": str(e), "status": 500}), 500
