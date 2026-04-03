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
    SimulationClient,
)

_SYNC_LOCK = threading.RLock()


def _sync_timeout_seconds():
    try:
        configured = float(app.config.get("sync_timeout_seconds", 300))
        if app.config.get("TESTING"):
            return max(0.0, configured)
        return max(5.0, configured)
    except Exception:
        return 300.0


def _ensure_sync_schema():
    with app.app_context():
        SimulationClient.__table__.create(bind=db.engine, checkfirst=True)


def _compute_next_time(day, hour, slots_per_day=24):
    if int(hour) < int(slots_per_day) - 1:
        return int(day), int(hour) + 1
    return int(day) + 1, 0


def _get_current_round_locked():
    cround = Rounds.query.order_by(desc(Rounds.id)).first()
    if cround is None:
        cround = Rounds(day=0, hour=0)
        db.session.add(cround)
        db.session.commit()
        cround = Rounds.query.order_by(desc(Rounds.id)).first()
    return cround


def _get_or_create_round_locked(day, hour):
    cround = Rounds.query.filter_by(day=int(day), hour=int(hour)).first()
    if cround is None:
        cround = Rounds(day=int(day), hour=int(hour))
        db.session.add(cround)
        db.session.commit()
        cround = Rounds.query.filter_by(day=int(day), hour=int(hour)).first()
    return cround


def _cleanup_stale_clients_locked(now_ts=None):
    timeout_s = _sync_timeout_seconds()
    now_ts = float(now_ts if now_ts is not None else pytime.time())
    stale_clients = (
        SimulationClient.query.filter_by(status="active")
        .filter(SimulationClient.last_heartbeat < (now_ts - timeout_s))
        .all()
    )
    for client in stale_clients:
        client.status = "stale"
        client.submitted_round_id = None
        client.updated_at = now_ts
    if stale_clients:
        db.session.commit()
    return stale_clients


def _active_clients_locked():
    return list(SimulationClient.query.filter_by(status="active").all())


def _try_advance_round_locked():
    current_round = _get_current_round_locked()
    _cleanup_stale_clients_locked()
    active_clients = _active_clients_locked()
    if not active_clients:
        return {
            "advanced": False,
            "round": current_round,
            "active_clients": 0,
            "submitted_clients": 0,
        }

    submitted_clients = [
        client for client in active_clients if int(client.submitted_round_id or -1) == int(current_round.id)
    ]
    if len(submitted_clients) < len(active_clients):
        return {
            "advanced": False,
            "round": current_round,
            "active_clients": len(active_clients),
            "submitted_clients": len(submitted_clients),
        }

    next_day, next_hour = _compute_next_time(current_round.day, current_round.hour)
    next_round = _get_or_create_round_locked(next_day, next_hour)
    now_ts = pytime.time()
    for client in active_clients:
        client.submitted_round_id = None
        client.updated_at = now_ts
    db.session.commit()
    return {
        "advanced": True,
        "round": next_round,
        "active_clients": len(active_clients),
        "submitted_clients": len(active_clients),
    }


def _round_payload(cround, **extra):
    payload = {"id": cround.id, "day": cround.day, "round": cround.hour}
    payload.update(extra)
    return payload


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
        _ensure_sync_schema()
        logging.debug("current_time: Querying database", extra={
            "thread_id": thread_id
        })
        with _SYNC_LOCK:
            return _get_current_round_locked()

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
    def _update_time(day, hour, force=False):
        _ensure_sync_schema()
        logging.debug("update_time: Querying database", extra={
            "thread_id": thread_id,
            "day": day,
            "hour": hour
        })
        with _SYNC_LOCK:
            _cleanup_stale_clients_locked()
            active_clients = _active_clients_locked()
            if active_clients and not force:
                current_round = _get_current_round_locked()
                return None, active_clients, current_round

            cround = _get_or_create_round_locked(day, hour)
            return cround, active_clients, cround

    try:
        data = json.loads(request.get_data())
        day = int(data["day"])
        hour = int(data["round"])
        force = bool(data.get("force"))

        cround, active_clients, current_round = _update_time(day, hour, force=force)
        if cround is None:
            return json.dumps(
                _round_payload(
                    current_round,
                    status=409,
                    error="sync_barrier_active",
                    active_clients=len(active_clients),
                )
            ), 409
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


@app.route("/register_client", methods=["POST"])
def register_client():
    try:
        data = json.loads(request.get_data() or "{}")
        client_id = str(data.get("client_id") or "").strip()
        if not client_id:
            return json.dumps({"status": 400, "error": "client_id_required"}), 400

        _ensure_sync_schema()
        with _SYNC_LOCK:
            current_round = _get_current_round_locked()
            now_ts = pytime.time()
            client = SimulationClient.query.filter_by(client_id=client_id).first()
            if client is None:
                client = SimulationClient(
                    client_id=client_id,
                    status="active",
                    last_heartbeat=now_ts,
                    created_at=now_ts,
                    updated_at=now_ts,
                )
                db.session.add(client)
            else:
                client.status = "active"
                client.last_heartbeat = now_ts
                client.submitted_round_id = None
                client.updated_at = now_ts
            db.session.commit()
            active_clients = len(_active_clients_locked())
        return json.dumps(_round_payload(current_round, status=200, client_id=client_id, active_clients=active_clients))
    except Exception as e:
        db.session.rollback()
        return json.dumps({"status": 500, "error": str(e)}), 500


@app.route("/heartbeat", methods=["POST"])
def heartbeat():
    try:
        data = json.loads(request.get_data() or "{}")
        client_id = str(data.get("client_id") or "").strip()
        if not client_id:
            return json.dumps({"status": 400, "error": "client_id_required"}), 400

        _ensure_sync_schema()
        with _SYNC_LOCK:
            client = SimulationClient.query.filter_by(client_id=client_id).first()
            if client is None:
                return json.dumps({"status": 404, "error": "client_not_registered"}), 404
            client.last_heartbeat = pytime.time()
            if client.status == "stale":
                client.status = "active"
            client.updated_at = client.last_heartbeat
            db.session.commit()
            current_round = _get_current_round_locked()
        return json.dumps(_round_payload(current_round, status=200, client_id=client_id))
    except Exception as e:
        db.session.rollback()
        return json.dumps({"status": 500, "error": str(e)}), 500


@app.route("/submit_round", methods=["POST"])
def submit_round():
    try:
        data = json.loads(request.get_data() or "{}")
        client_id = str(data.get("client_id") or "").strip()
        round_id = int(data.get("round_id"))
        if not client_id:
            return json.dumps({"status": 400, "error": "client_id_required"}), 400

        _ensure_sync_schema()
        with _SYNC_LOCK:
            _cleanup_stale_clients_locked()
            current_round = _get_current_round_locked()
            client = SimulationClient.query.filter_by(client_id=client_id).first()
            if client is None:
                return json.dumps(_round_payload(current_round, status=404, error="client_not_registered")), 404
            if client.status != "active":
                return json.dumps(_round_payload(current_round, status=409, error="client_not_active")), 409
            client.last_heartbeat = pytime.time()
            client.updated_at = client.last_heartbeat

            if int(current_round.id) != round_id:
                db.session.commit()
                return json.dumps(
                    _round_payload(
                        current_round,
                        status=409,
                        error="round_mismatch",
                        submitted_round_id=round_id,
                    )
                ), 409

            client.submitted_round_id = round_id
            db.session.commit()
            result = _try_advance_round_locked()
            round_payload = _round_payload(
                result["round"],
                status=200,
                advanced=bool(result["advanced"]),
                active_clients=int(result["active_clients"]),
                submitted_clients=int(result["submitted_clients"]),
            )
        return json.dumps(round_payload)
    except Exception as e:
        db.session.rollback()
        return json.dumps({"status": 500, "error": str(e)}), 500


@app.route("/complete_client", methods=["POST"])
def complete_client():
    try:
        data = json.loads(request.get_data() or "{}")
        client_id = str(data.get("client_id") or "").strip()
        if not client_id:
            return json.dumps({"status": 400, "error": "client_id_required"}), 400

        _ensure_sync_schema()
        with _SYNC_LOCK:
            current_round = _get_current_round_locked()
            client = SimulationClient.query.filter_by(client_id=client_id).first()
            if client is None:
                return json.dumps(_round_payload(current_round, status=404, error="client_not_registered")), 404
            now_ts = pytime.time()
            client.status = "completed"
            client.submitted_round_id = None
            client.last_heartbeat = now_ts
            client.updated_at = now_ts
            db.session.commit()
            result = _try_advance_round_locked()
            active_clients = len(_active_clients_locked())
        return json.dumps(
            _round_payload(
                result["round"],
                status=200,
                advanced=bool(result["advanced"]),
                active_clients=active_clients,
            )
        )
    except Exception as e:
        db.session.rollback()
        return json.dumps({"status": 500, "error": str(e)}), 500


@app.route("/deregister_client", methods=["POST"])
def deregister_client():
    try:
        data = json.loads(request.get_data() or "{}")
        client_id = str(data.get("client_id") or "").strip()
        if not client_id:
            return json.dumps({"status": 400, "error": "client_id_required"}), 400

        _ensure_sync_schema()
        with _SYNC_LOCK:
            current_round = _get_current_round_locked()
            client = SimulationClient.query.filter_by(client_id=client_id).first()
            if client is not None:
                db.session.delete(client)
                db.session.commit()
            result = _try_advance_round_locked()
        return json.dumps(_round_payload(result["round"], status=200, advanced=bool(result["advanced"])))
    except Exception as e:
        db.session.rollback()
        return json.dumps({"status": 500, "error": str(e)}), 500
