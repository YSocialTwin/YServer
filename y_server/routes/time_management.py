import json
import time as pytime
from functools import wraps

from flask import request
from sqlalchemy import desc
from sqlalchemy.exc import OperationalError
from y_server import app, db
from y_server.modals import (
    Rounds,
)


def retry_on_db_lock(max_retries=3, delay=0.5):
    """
    Decorator to retry database operations when SQLite database is locked.
    This handles the "database is locked" error by waiting and retrying.
    
    :param max_retries: Maximum number of retry attempts
    :param delay: Delay between retries in seconds
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
                            # Wait before retrying
                            pytime.sleep(delay * (attempt + 1))  # Exponential backoff
                            continue
                    raise
                except Exception:
                    raise
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
    @retry_on_db_lock(max_retries=3, delay=0.5)
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
    @retry_on_db_lock(max_retries=3, delay=0.5)
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
