from __future__ import annotations

import json
import shutil
import sys
import uuid
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from y_server import app, db
from y_server.modals import Rounds, StressReward, User_mgmt
from y_server.schema_migrations import ensure_moderation_schema


def _post_json(client, path, payload):
    return client.post(path, data=json.dumps(payload), content_type="application/json")


@pytest.fixture()
def client(tmp_path):
    exp_dir = tmp_path / "experiment"
    exp_dir.mkdir()
    db_path = exp_dir / "database_server.db"
    shutil.copyfile(ROOT / "data_schema" / "database_clean_server.db", db_path)

    app.config["TESTING"] = True
    app.config["stress_reward_enabled"] = True
    client = app.test_client()

    resp = _post_json(client, "/change_db", {"path": str(db_path)})
    assert resp.status_code == 200
    resp = _post_json(client, "/reset", {})
    assert resp.status_code == 200
    with app.app_context():
        ensure_moderation_schema(db.engine)

    with app.app_context():
        db.session.remove()

    yield client

    with app.app_context():
        db.session.remove()


def test_set_and_get_stress_reward_roundtrip(client):
    with app.app_context():
        with db.engine.begin() as conn:
            conn.exec_driver_sql(
                "INSERT INTO user_mgmt (username, email, password, joined_on) VALUES (?, ?, ?, ?)",
                ("stress-user", "", "pwd", 0),
            )
            user_id = conn.exec_driver_sql(
                "SELECT id FROM user_mgmt WHERE username = ?", ("stress-user",)
            ).scalar()
            for rid in (1, 2, 3):
                conn.exec_driver_sql(
                    "INSERT OR IGNORE INTO rounds (id, day, hour) VALUES (?, ?, ?)",
                    (rid, 0, rid),
                )
            conn.exec_driver_sql(
                "INSERT INTO stress_reward (id, uid, variable, value, type, tid) VALUES (?, ?, ?, ?, ?, ?)",
                (str(uuid.uuid4()), user_id, "stress", 0.2, "aggregate", 1),
            )
            conn.exec_driver_sql(
                "INSERT INTO stress_reward (id, uid, variable, value, type, tid) VALUES (?, ?, ?, ?, ?, ?)",
                (str(uuid.uuid4()), user_id, "reward", 0.4, "aggregate", 1),
            )

    set_resp = _post_json(
        client,
        "/set_stress_reward_variations",
        {
            "user_id": user_id,
            "tid": 2,
            "action": "reaction:like",
            "variations": [
                {"variable": "stress", "value": 0.1},
                {"variable": "reward", "value": -0.05},
            ],
        },
    )
    assert json.loads(set_resp.data)["written"] == 2

    get_resp = _post_json(
        client,
        "/get_stress_reward",
        {"user_id": user_id, "tid": 3, "backward_rounds": 5},
    )
    payload = json.loads(get_resp.data)
    assert payload["status"] == 200
    assert payload["stress"] == pytest.approx(0.3)
    assert payload["reward"] == pytest.approx(0.35)

    with app.app_context():
        aggregates = StressReward.query.filter_by(uid=user_id, type="aggregate", tid=3).all()
        aggregate_map = {row.variable: row.value for row in aggregates}
        assert aggregate_map["stress"] == pytest.approx(0.3)
        assert aggregate_map["reward"] == pytest.approx(0.35)
        variation_actions = {
            (row.variable, row.value): row.action
            for row in StressReward.query.filter_by(uid=user_id, type="variation", tid=2).all()
        }
        assert variation_actions[("stress", 0.1)] == "reaction:like"
        assert variation_actions[("reward", -0.05)] == "reaction:like"


def test_get_stress_reward_includes_same_round_variations_after_aggregate(client):
    with app.app_context():
        with db.engine.begin() as conn:
            conn.exec_driver_sql(
                "INSERT INTO user_mgmt (username, email, password, joined_on) VALUES (?, ?, ?, ?)",
                ("same-round-user", "", "pwd", 0),
            )
            user_id = conn.exec_driver_sql(
                "SELECT id FROM user_mgmt WHERE username = ?", ("same-round-user",)
            ).scalar()
            conn.exec_driver_sql(
                "INSERT OR IGNORE INTO rounds (id, day, hour) VALUES (?, ?, ?)",
                (1, 0, 1),
            )
            conn.exec_driver_sql(
                "INSERT INTO stress_reward (id, uid, variable, value, type, tid) VALUES (?, ?, ?, ?, ?, ?)",
                (str(uuid.uuid4()), user_id, "stress", 0.0, "aggregate", 1),
            )
            conn.exec_driver_sql(
                "INSERT INTO stress_reward (id, uid, variable, value, type, tid) VALUES (?, ?, ?, ?, ?, ?)",
                (str(uuid.uuid4()), user_id, "reward", 0.0, "aggregate", 1),
            )
            conn.exec_driver_sql(
                "INSERT INTO stress_reward (id, uid, variable, value, type, tid) VALUES (?, ?, ?, ?, ?, ?)",
                (str(uuid.uuid4()), user_id, "stress", 0.2, "variation", 1),
            )
            conn.exec_driver_sql(
                "INSERT INTO stress_reward (id, uid, variable, value, type, tid) VALUES (?, ?, ?, ?, ?, ?)",
                (str(uuid.uuid4()), user_id, "reward", 0.15, "variation", 1),
            )

    get_resp = _post_json(
        client,
        "/get_stress_reward",
        {"user_id": user_id, "tid": 1, "backward_rounds": 5},
    )
    payload = json.loads(get_resp.data)
    assert payload["status"] == 200
    assert payload["stress"] == pytest.approx(0.2)
    assert payload["reward"] == pytest.approx(0.15)


def test_timeline_counts_posts_reactions_comments_and_reposts(client):
    with app.app_context():
        with db.engine.begin() as conn:
            conn.exec_driver_sql(
                "INSERT INTO user_mgmt (username, email, password, joined_on) VALUES (?, ?, ?, ?)",
                ("timeline-user", "timeline-user@example.com", "pwd", 0),
            )
            conn.exec_driver_sql(
                "INSERT INTO user_mgmt (username, email, password, joined_on) VALUES (?, ?, ?, ?)",
                ("timeline-peer", "timeline-peer@example.com", "pwd", 0),
            )
            author_id = conn.exec_driver_sql(
                "SELECT id FROM user_mgmt WHERE username = ?", ("timeline-user",)
            ).scalar()
            peer_id = conn.exec_driver_sql(
                "SELECT id FROM user_mgmt WHERE username = ?", ("timeline-peer",)
            ).scalar()
            conn.exec_driver_sql(
                "INSERT OR IGNORE INTO rounds (id, day, hour) VALUES (?, ?, ?)",
                (1, 0, 1),
            )
            conn.exec_driver_sql(
                "INSERT INTO post (id, tweet, round, user_id, comment_to, thread_id, shared_from, moderated, is_moderation_comment) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (10, "root", 1, author_id, -1, 10, -1, 0, 0),
            )
            conn.exec_driver_sql(
                "INSERT INTO post (id, tweet, round, user_id, comment_to, thread_id, shared_from, moderated, is_moderation_comment) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (11, "comment", 1, peer_id, 10, 10, -1, 0, 0),
            )
            conn.exec_driver_sql(
                "INSERT INTO post (id, tweet, round, user_id, comment_to, thread_id, shared_from, moderated, is_moderation_comment) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (12, "share", 1, peer_id, -1, 12, 10, 0, 0),
            )
            conn.exec_driver_sql(
                "INSERT INTO reactions (round, user_id, post_id, type) VALUES (?, ?, ?, ?)",
                (1, peer_id, 10, "like"),
            )
            conn.exec_driver_sql(
                "INSERT INTO reactions (round, user_id, post_id, type) VALUES (?, ?, ?, ?)",
                (1, author_id, 10, "dislike"),
            )

    timeline_resp = client.get(
        "/timeline",
        data=json.dumps({"user_id": author_id}),
        content_type="application/json",
    )
    payload = json.loads(timeline_resp.data)
    assert payload == [
        {
            "post_id": 10,
            "post": "root",
            "round": 1,
            "reposts": 1,
            "likes": 1,
            "dislikes": 1,
            "comments": 1,
        }
    ]
