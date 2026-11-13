"""Offline participation: a person plays while the server is not running.

One request is applied to the database of the experiment by the same `HumanGateway`, in a short-lived process, under an
exclusive file lock so that two requests never write at once. When the server is running the request is refused (409):
the person goes through the online gateway instead."""

from __future__ import annotations

import fcntl
import json
import urllib.request
from pathlib import Path
from typing import Any, Callable

OFFLINE_OPS = ("ensure", "state", "actions")


def server_running(host: str, port: int, timeout: float = 1.0) -> bool:
    """True when something answers /status on the address of the server of the experiment."""
    host = "127.0.0.1" if host in ("0.0.0.0", "", None) else host
    try:
        with urllib.request.urlopen(f"http://{host}:{int(port)}/status", timeout=timeout) as resp:  # noqa: S310 - loopback
            return resp.status == 200
    except Exception:  # noqa: BLE001 - nothing answers: stopped
        return False


def handle_offline(lock_path, op: str, body: Any, gateway_factory: Callable[[], Any], running: Callable[[], bool]) -> tuple[int, dict]:
    """Apply one request. `gateway_factory()` builds the HumanGateway on the database of the experiment (called only
    once the lock is held and the server is known to be stopped)."""
    from .core import dispatch

    if op not in OFFLINE_OPS:
        return 409, {"ok": False, "code": "not_available_offline"}
    if not isinstance(body, dict):
        return 400, {"ok": False, "code": "invalid_request"}
    with open(lock_path, "a+") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        try:
            if running():
                return 409, {"ok": False, "code": "server_running"}
            gw = gateway_factory()
            if op == "state":
                return dispatch(gw, "GET", ["v1", "state"], {}, body)
            parts = ["v1", "humans", "ensure"] if op == "ensure" else ["v1", "actions"]
            return dispatch(gw, "POST", parts, {}, body)
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)


def main_json(raw: str) -> dict:
    try:
        data = json.loads(raw or "{}")
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}
