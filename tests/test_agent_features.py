import json
import shutil
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from y_server import app, db
from y_server.modals import Agent_Custom_Feature, Agent_Opinion, User_mgmt


def _post_json(client, path, payload):
    return client.post(path, data=json.dumps(payload), content_type="application/json")


def _register_user(client, *, name, email, leaning="center"):
    response = _post_json(
        client,
        "/register",
        {
            "name": name,
            "email": email,
            "password": "secret",
            "leaning": leaning,
            "age": 30,
            "user_type": "agent",
            "oe": "0.5",
            "co": "0.5",
            "ex": "0.5",
            "ag": "0.5",
            "ne": "0.5",
            "language": "en",
            "education_level": "college",
            "joined_on": 0,
            "round_actions": 5,
            "owner": "tests",
            "gender": "na",
            "nationality": "IT",
            "toxicity": "low",
            "daily_activity_level": 1,
            "activity_profile": "Always On",
            "profession": "tester",
        },
    )
    assert response.status_code == 200


@pytest.fixture()
def client(tmp_path):
    exp_dir = tmp_path / "experiment"
    exp_dir.mkdir()
    db_path = exp_dir / "database_server.db"
    shutil.copyfile(ROOT / "data_schema" / "database_clean_server.db", db_path)

    app.config["TESTING"] = True
    client = app.test_client()

    response = _post_json(client, "/change_db", {"path": str(db_path)})
    assert response.status_code == 200
    response = _post_json(client, "/reset", {})
    assert response.status_code == 200

    with app.app_context():
        db.session.remove()

    yield client

    with app.app_context():
        db.session.remove()


def test_stubborn_opinions_are_not_updated(client):
    _register_user(client, name="alice", email="alice@example.org")

    response = _post_json(
        client,
        "/set_user_opinions",
        {
            "user_id": 1,
            "round": 1,
            "opinions": {"climate": 0.25},
            "stubborn_topics": ["climate"],
            "id_interacted_with": -1,
            "id_post": -1,
        },
    )
    assert response.status_code == 200

    response = _post_json(
        client,
        "/set_user_opinions",
        {
            "user_id": 1,
            "round": 2,
            "opinions": {"climate": 0.9},
            "id_interacted_with": -1,
            "id_post": -1,
        },
    )
    assert response.status_code == 200

    with app.app_context():
        latest = (
            Agent_Opinion.query.filter_by(agent_id=1)
            .order_by(Agent_Opinion.tid.desc(), Agent_Opinion.id.desc())
            .first()
        )
        assert latest.opinion == pytest.approx(0.25)
        assert latest.stubborn == 1


def test_user_custom_features_round_trip(client):
    _register_user(client, name="alice", email="alice@example.org")

    response = _post_json(
        client,
        "/set_user_custom_features",
        {
            "user_id": 1,
            "custom_features": {"Class": "Mage", "Guild": "North"},
        },
    )
    assert response.status_code == 200

    response = _post_json(client, "/get_user_custom_features", {"user_id": 1})
    assert response.status_code == 200
    body = json.loads(response.get_data(as_text=True))
    assert {item["key"]: item["value"] for item in body} == {
        "Class": "Mage",
        "Guild": "North",
    }

    with app.app_context():
        assert Agent_Custom_Feature.query.filter_by(user_id=1).count() == 2


def test_churn_route_supports_explicit_user_id(client):
    _register_user(client, name="alice", email="alice@example.org")

    response = _post_json(client, "/churn", {"user_id": 1, "left_on": 12})
    assert response.status_code == 200

    body = json.loads(response.get_data(as_text=True))
    assert body["status"] == 200
    assert body["removed"] == {"1": None}

    with app.app_context():
        assert User_mgmt.query.filter_by(id=1).first().left_on == 12
