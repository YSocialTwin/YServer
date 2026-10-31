"""Federated clock hooks of YServer (F2.3). The gate is replaced by a stub: no coordinator, no network."""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from y_server import app, db
from y_server.routes import time_management as tm


def _post_json(client, path, payload):
    return client.post(path, data=json.dumps(payload), content_type="application/json")


class StubGate:
    def __init__(self):
        self.allowed = True
        self.calls = []

    def on_barrier_ready(self, local_round):
        self.calls.append(("barrier", tuple(local_round)))
        return self.allowed

    def on_round_opened(self, local_round):
        self.calls.append(("opened", tuple(local_round)))

    def on_finished(self):
        self.calls.append(("finished",))

    def start(self, local_round):
        self.calls.append(("start", tuple(local_round)))


@pytest.fixture()
def client(tmp_path):
    exp_dir = tmp_path / "experiment"
    exp_dir.mkdir()
    db_path = exp_dir / "database_server.db"
    shutil.copyfile(ROOT / "data_schema" / "database_clean_server.db", db_path)
    app.config["TESTING"] = True
    app.config["sync_timeout_seconds"] = 300
    client = app.test_client()
    assert _post_json(client, "/change_db", {"path": str(db_path)}).status_code == 200
    assert _post_json(client, "/reset", {}).status_code == 200
    with app.app_context():
        db.session.remove()
    yield client
    tm._federation_gate = None
    tm._federation_pending = False
    with app.app_context():
        db.session.remove()


@pytest.fixture()
def gate():
    g = StubGate()
    tm._federation_gate = g
    return g


def test_standalone_by_default():
    assert tm._federation_gate is None and tm._federation_pending is False


def test_gate_holds_the_round_and_current_time_releases_it(client, gate):
    start = json.loads(client.get("/current_time").data)
    _post_json(client, "/register_client", {"client_id": "a"})
    gate.allowed = False
    submit = json.loads(_post_json(client, "/submit_round", {"client_id": "a", "round_id": start["id"]}).data)
    assert submit["advanced"] is False
    assert gate.calls == [("barrier", (0, 0))]
    still = json.loads(client.get("/current_time").data)  # a poll while the gate is closed: still held
    assert still["id"] == start["id"] and tm._federation_pending is True
    gate.allowed = True
    after = json.loads(client.get("/current_time").data)  # the poll retries the advance
    assert after["id"] != start["id"] and (after["day"], after["round"]) == (0, 1)
    assert ("opened", (0, 1)) in gate.calls and tm._federation_pending is False


def test_open_gate_advances_at_once_and_reports_the_new_round(client, gate):
    start = json.loads(client.get("/current_time").data)
    _post_json(client, "/register_client", {"client_id": "a"})
    submit = json.loads(_post_json(client, "/submit_round", {"client_id": "a", "round_id": start["id"]}).data)
    assert submit["advanced"] is True
    assert gate.calls == [("barrier", (0, 0)), ("opened", (0, 1))]


def test_day_boundary_is_reported_in_the_runtime_numbering(client, gate):
    _post_json(client, "/register_client", {"client_id": "a"})
    for _ in range(24):
        cur = json.loads(client.get("/current_time").data)
        assert json.loads(_post_json(client, "/submit_round", {"client_id": "a", "round_id": cur["id"]}).data)["advanced"]
    assert gate.calls[-2:] == [("barrier", (0, 23)), ("opened", (1, 0))]


def test_barrier_not_asked_while_local_clients_are_missing(client, gate):
    start = json.loads(client.get("/current_time").data)
    _post_json(client, "/register_client", {"client_id": "a"})
    _post_json(client, "/register_client", {"client_id": "b"})
    _post_json(client, "/submit_round", {"client_id": "a", "round_id": start["id"]})
    assert gate.calls == []  # the local barrier comes first (step 1 of the tick)


def test_end_of_run_is_reported_once_all_clients_completed(client, gate):
    _post_json(client, "/register_client", {"client_id": "a"})
    _post_json(client, "/register_client", {"client_id": "b"})
    _post_json(client, "/complete_client", {"client_id": "a"})
    assert ("finished",) not in gate.calls
    _post_json(client, "/complete_client", {"client_id": "b"})
    assert ("finished",) in gate.calls


def test_init_federation_is_a_noop_without_the_section():
    from y_server.federation import init_federation

    assert init_federation({}) is None
    assert init_federation({"federation": {"enabled": False, "member": "x"}}) is None
    assert tm._federation_gate is None


def test_safe_gate_swallows_opening_errors():
    from y_server.federation.gate import SafeGate

    class Broken(StubGate):
        def on_round_opened(self, r):
            raise RuntimeError("coordinator down")

        def on_finished(self):
            raise RuntimeError("coordinator down")

    safe = SafeGate(Broken())
    safe.on_round_opened((0, 1))  # logged, not raised
    safe.on_finished()
    assert safe.on_barrier_ready((0, 0)) is True
    safe.start((0, 0))
    assert safe.gate.calls[-1] == ("start", (0, 0))


def test_adapter_clock_and_conformance():
    pytest.importorskip("ysocial_federation")
    from y_server.federation.adapter import YServerAdapter
    from ysocial_federation.testing.conformance import ConformanceCase, run_all

    case = ConformanceCase(lambda: YServerAdapter("micro", 1), (0, 0),
                           lambda r: (r[0], r[1] + 1) if r[1] < 23 else (r[0] + 1, 0), "micro", 1)
    assert "consecutive_ticks" in run_all(case)
