from __future__ import annotations

import json
import shutil
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from y_server import app, db


def _post_json(client, path, payload):
    return client.post(path, data=json.dumps(payload), content_type="application/json")


@pytest.fixture()
def client(tmp_path):
    exp_dir = tmp_path / "experiment"
    exp_dir.mkdir()
    db_path = exp_dir / "database_server.db"
    shutil.copyfile(ROOT / "data_schema" / "database_clean_server.db", db_path)

    app.config["TESTING"] = True
    app.config["sync_timeout_seconds"] = 300
    client = app.test_client()

    resp = _post_json(client, "/change_db", {"path": str(db_path)})
    assert resp.status_code == 200
    resp = _post_json(client, "/reset", {})
    assert resp.status_code == 200

    with app.app_context():
        db.session.remove()

    yield client

    with app.app_context():
        db.session.remove()


def test_single_client_submit_advances_immediately(client):
    current = json.loads(client.get("/current_time").data)
    reg = json.loads(_post_json(client, "/register_client", {"client_id": "client-a"}).data)
    assert reg["id"] == current["id"]

    submit = json.loads(
        _post_json(client, "/submit_round", {"client_id": "client-a", "round_id": current["id"]}).data
    )
    assert submit["status"] == 200
    assert submit["advanced"] is True
    assert submit["id"] != current["id"]


def test_two_clients_require_barrier_before_advancing(client):
    current = json.loads(client.get("/current_time").data)
    _post_json(client, "/register_client", {"client_id": "client-a"})
    _post_json(client, "/register_client", {"client_id": "client-b"})

    submit_a = json.loads(
        _post_json(client, "/submit_round", {"client_id": "client-a", "round_id": current["id"]}).data
    )
    assert submit_a["advanced"] is False

    still_current = json.loads(client.get("/current_time").data)
    assert still_current["id"] == current["id"]

    submit_b = json.loads(
        _post_json(client, "/submit_round", {"client_id": "client-b", "round_id": current["id"]}).data
    )
    assert submit_b["advanced"] is True
    assert submit_b["id"] != current["id"]


def test_completed_client_does_not_block_barrier(client):
    current = json.loads(client.get("/current_time").data)
    _post_json(client, "/register_client", {"client_id": "client-a"})
    _post_json(client, "/register_client", {"client_id": "client-b"})

    complete_b = json.loads(_post_json(client, "/complete_client", {"client_id": "client-b"}).data)
    assert complete_b["status"] == 200

    submit_a = json.loads(
        _post_json(client, "/submit_round", {"client_id": "client-a", "round_id": current["id"]}).data
    )
    assert submit_a["advanced"] is True


def test_remaining_client_continues_after_other_client_completes(client):
    current = json.loads(client.get("/current_time").data)
    _post_json(client, "/register_client", {"client_id": "client-a"})
    _post_json(client, "/register_client", {"client_id": "client-b"})

    submit_a_round_zero = json.loads(
        _post_json(client, "/submit_round", {"client_id": "client-a", "round_id": current["id"]}).data
    )
    assert submit_a_round_zero["advanced"] is False

    submit_b_round_zero = json.loads(
        _post_json(client, "/submit_round", {"client_id": "client-b", "round_id": current["id"]}).data
    )
    assert submit_b_round_zero["advanced"] is True
    assert submit_b_round_zero["round"] == 1

    round_one = json.loads(client.get("/current_time").data)
    submit_a_round_one = json.loads(
        _post_json(client, "/submit_round", {"client_id": "client-a", "round_id": round_one["id"]}).data
    )
    assert submit_a_round_one["advanced"] is False
    assert submit_a_round_one["round"] == 1
    assert submit_a_round_one["active_clients"] == 2
    assert submit_a_round_one["submitted_clients"] == 1

    complete_b = json.loads(_post_json(client, "/complete_client", {"client_id": "client-b"}).data)
    assert complete_b["advanced"] is True
    assert complete_b["round"] == 2
    assert complete_b["active_clients"] == 1

    round_two = json.loads(client.get("/current_time").data)
    assert round_two["round"] == 2

    submit_a_round_two = json.loads(
        _post_json(client, "/submit_round", {"client_id": "client-a", "round_id": round_two["id"]}).data
    )
    assert submit_a_round_two["advanced"] is True
    assert submit_a_round_two["round"] == 3
    assert submit_a_round_two["active_clients"] == 1


def test_stale_client_is_removed_from_blocking_set(client):
    app.config["sync_timeout_seconds"] = 0.05
    current = json.loads(client.get("/current_time").data)
    _post_json(client, "/register_client", {"client_id": "client-a"})
    _post_json(client, "/register_client", {"client_id": "client-b"})

    time.sleep(0.08)
    hb = _post_json(client, "/heartbeat", {"client_id": "client-a"})
    assert hb.status_code == 200

    submit_a = json.loads(
        _post_json(client, "/submit_round", {"client_id": "client-a", "round_id": current["id"]}).data
    )
    assert submit_a["advanced"] is True
