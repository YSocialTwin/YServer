import json
import logging
import time as pytime
from functools import wraps

from flask import request
from sqlalchemy import desc
from sqlalchemy.exc import OperationalError
from y_server import app, db
from y_server.modals import (
    Rounds,
)


def force_release_sqlite_lock():
    """
    Force release SQLite database lock by closing all connections and disposing the engine.
    This is a last resort when retries fail and the database remains locked.
    """
    try:
        # Remove the current session
        db.session.remove()
        # Dispose the engine to close all connections in the pool
        db.engine.dispose()
        logging.warning("Force released SQLite database lock by disposing engine connections")
        return True
    except Exception as e:
        logging.error(f"Failed to force release SQLite lock: {str(e)}")
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
            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except OperationalError as e:
                    if "database is locked" in str(e).lower():
                        last_exception = e
                        if attempt < max_retries:
                            # Rollback the failed transaction
                            try:
                                db.session.rollback()
                            except Exception:
                                pass
                            # Wait before retrying with exponential backoff
                            pytime.sleep(delay * (attempt + 1))
                            continue
                    else:
                        raise
                except Exception:
                    raise
            
            # If we've exhausted all retries and still have a lock error
            if last_exception and force_release_on_failure:
                logging.warning(f"All {max_retries} retries failed due to database lock. Attempting force release...")
                # Force release the lock
                if force_release_sqlite_lock():
                    # Wait a moment for the lock to be fully released
                    pytime.sleep(0.5)
                    # Try one final time after force release
                    try:
                        return func(*args, **kwargs)
                    except Exception as final_e:
                        logging.error(f"Operation failed even after force lock release: {str(final_e)}")
                        raise final_e
            
            # If we've exhausted all retries, raise the last exception
            if last_exception:
                raise last_exception
        return wrapper
    return decorator


@app.route("/current_time", methods=["GET"])
def current_time():
    """
    Get the current time of the simulation.

    :return: a json object with the current time
    """
    @retry_on_db_lock(max_retries=3, delay=0.5, force_release_on_failure=True)
    def _get_current_time():
        cround = Rounds.query.order_by(desc(Rounds.id)).first()
        if cround is None:
            cround = Rounds(day=0, hour=0)
            db.session.add(cround)
            db.session.commit()
            cround = Rounds.query.order_by(desc(Rounds.id)).first()
        return cround

    try:
        cround = _get_current_time()
        return json.dumps({"id": cround.id, "day": cround.day, "round": cround.hour})
    except Exception as e:
        # Rollback any failed transaction
        try:
            db.session.rollback()
        except Exception:
            pass
        return json.dumps({"error": str(e), "status": 500}), 500


@app.route("/update_time", methods=["POST"])
def update_time():
    """
    Update the time of the simulation.

    :return: a json object with the updated time
    """
    @retry_on_db_lock(max_retries=3, delay=0.5, force_release_on_failure=True)
    def _update_time(day, hour):
        cround = Rounds.query.filter_by(day=day, hour=hour).first()
        if cround is None:
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
        return json.dumps({"id": cround.id, "day": cround.day, "round": cround.hour})
    except Exception as e:
        # Rollback any failed transaction
        try:
            db.session.rollback()
        except Exception:
            pass
        return json.dumps({"error": str(e), "status": 500}), 500
