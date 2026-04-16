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


def _post_json(client, path, payload):
    return client.post(path, data=json.dumps(payload), content_type="application/json")


@pytest.fixture()
def client(tmp_path):
    exp_dir = tmp_path / "experiment"
    exp_dir.mkdir()
    db_path = exp_dir / "database_server.db"
    shutil.copyfile(ROOT / "data_schema" / "database_clean_server.db", db_path)

    app.config["TESTING"] = True
    client = app.test_client()
    assert _post_json(client, "/change_db", {"path": str(db_path)}).status_code == 200
    assert _post_json(client, "/reset", {}).status_code == 200
    yield client


def test_check_follow_relationship_returns_latest_edge_state(client):
    with app.app_context():
        with db.engine.begin() as conn:
            conn.exec_driver_sql(
                "INSERT INTO rounds (id, day, hour) VALUES (?, ?, ?)", (1, 0, 1)
            )
            conn.exec_driver_sql(
                "INSERT INTO rounds (id, day, hour) VALUES (?, ?, ?)", (2, 0, 2)
            )
            conn.exec_driver_sql(
                "INSERT INTO user_mgmt (id, username, email, password, joined_on) VALUES (?, ?, ?, ?, ?)",
                (1, "alice", "alice@example.test", "pwd", 0),
            )
            conn.exec_driver_sql(
                "INSERT INTO user_mgmt (id, username, email, password, joined_on) VALUES (?, ?, ?, ?, ?)",
                (2, "bob", "bob@example.test", "pwd", 0),
            )
            conn.exec_driver_sql(
                "INSERT INTO follow (follower_id, user_id, action, round) VALUES (?, ?, ?, ?)",
                (1, 2, "follow", 1),
            )
            conn.exec_driver_sql(
                "INSERT INTO follow (follower_id, user_id, action, round) VALUES (?, ?, ?, ?)",
                (1, 2, "unfollow", 2),
            )

    payload = json.loads(
        _post_json(
            client, "/check_follow_relationship", {"follower_id": 1, "user_id": 2}
        ).data
    )

    assert payload["status"] == 200
    assert payload["is_following"] is False
