"""Human gateway of YServer: account, actions through the routes of the server, federation marks, offline mode."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading

import pytest

from tests.test_federation_bus import _post_json, client  # noqa: F401  (fixture)
from y_server import app, db
from y_server.gateway.core import HumanGateway
from y_server.gateway.offline import handle_offline
from y_server.modals import Follow, Post, Reactions, User_mgmt
from sqlalchemy import select

TOKEN = "t0ken"
H = {"X-YServer-Gateway-Token": TOKEN}


@pytest.fixture()
def gw(client):  # noqa: F811
    app.config["human_gateway_token"] = TOKEN
    yield client
    app.config.pop("human_gateway_token", None)


def gpost(c, path, body, headers=H):
    r = c.post(path, data=json.dumps(body), content_type="application/json", headers=headers)
    return r.status_code, r.get_json()


def enrol(c, key="k1", name="ann_h", human_id="human:7"):
    status, out = gpost(c, "/gateway/v1/humans/ensure", {"human_key": key, "username": name, "human_id": human_id})
    assert status == 200, out
    return out["account_id"]


def test_the_gateway_is_off_without_a_token_and_needs_the_header(client):  # noqa: F811
    assert gpost(client, "/gateway/v1/state", {}, {})[0] == 404
    app.config["human_gateway_token"] = TOKEN
    try:
        assert gpost(client, "/gateway/v1/humans/ensure", {}, {})[0] == 401
        assert gpost(client, "/gateway/v1/humans/ensure", {}, {"X-YServer-Gateway-Token": "bad"})[0] == 401
        assert gpost(client, "/gateway/v1/nothing", {})[0] == 404
    finally:
        app.config.pop("human_gateway_token", None)


def test_ensure_is_idempotent_and_never_adopts_an_existing_account(gw):
    first = enrol(gw)
    assert enrol(gw) == first
    with app.app_context():
        assert db.session.get(User_mgmt, first).username == "ann_h"
    status, out = gpost(gw, "/gateway/v1/humans/ensure", {"human_key": "k2", "username": "u1"})  # u1 is an agent's account
    assert (status, out["code"]) == (409, "username_taken")
    assert gpost(gw, "/gateway/v1/humans/ensure", {"human_key": "k1", "username": "ann_h", "human_id": "human:8"})[0] == 409
    assert gpost(gw, "/gateway/v1/humans/ensure", {"human_key": "k3", "username": "bad name!"})[0] == 400
    assert gpost(gw, "/gateway/v1/humans/ensure", {"human_key": "k3", "username": "okname", "human_id": "agent:1"})[0] == 400


def test_the_actions_go_through_the_routes_of_the_server(gw):
    uid = enrol(gw)
    status, out = gpost(gw, "/gateway/v1/actions", {"account_id": uid, "actions": [
        {"type": "post", "text": "hello #world @u1"},
        {"type": "reaction", "post_id": 1, "reaction": "like"}, {"type": "follow", "target": 1}]})
    assert status == 200 and out["ok"], out
    post_id = out["results"][0]["post_id"]
    status, out = gpost(gw, "/gateway/v1/actions", {"account_id": uid, "actions": [
        {"type": "comment", "post_id": post_id, "text": "a reply"}, {"type": "share", "post_id": post_id, "text": "sharing"},
        {"type": "unfollow", "target": 1}]})
    assert status == 200 and out["ok"], out
    with app.app_context():
        posts = db.session.scalars(select(Post).filter_by(user_id=uid).order_by(Post.id)).all()
        assert [(p.tweet.strip(), p.comment_to, p.shared_from) for p in posts][0][0].startswith("hello")
        assert posts[1].comment_to == post_id and posts[2].shared_from == post_id
        assert db.session.scalars(select(Reactions).filter_by(user_id=uid, post_id=1, type="like")).first() is not None
        assert [f.action for f in db.session.scalars(select(Follow).filter_by(user_id=uid, follower_id=1)).all()] == ["follow", "unfollow"]


def test_invalid_requests_and_foreign_accounts_are_refused(gw):
    uid = enrol(gw)
    assert gpost(gw, "/gateway/v1/actions", {"account_id": 1, "actions": [{"type": "post", "text": "x"}]})[0] == 403  # an agent
    assert gpost(gw, "/gateway/v1/actions", {"account_id": uid, "actions": []})[0] == 400
    status, out = gpost(gw, "/gateway/v1/actions", {"account_id": uid, "actions": [
        {"type": "post", "text": ""}, {"type": "reaction", "post_id": 1, "reaction": "love"}, {"type": "fly"},
        {"type": "post", "text": "x", "crosspost_to": []}]})
    assert status == 200 and not out["ok"] and [r["status"] for r in out["results"]] == [400, 400, 400, 400]


def test_a_person_post_with_targets_leaves_as_a_crosspost_with_the_human_identity(gw):
    from y_server.federation.adapter import YServerAdapter

    a = YServerAdapter("micro", 1, accounts={"g1": 1, "g2": 2, "human:7": 10}, crosspost_mode="agent_action")
    app.config["federation_adapter"] = a
    try:
        with app.app_context():
            uid = None
        status, out = gpost(gw, "/gateway/v1/humans/ensure", {"human_key": "k", "username": "ann_h", "human_id": "human:7"})
        uid = out["account_id"]
        a._accounts["human:7"] = uid
        a._by_user[uid] = "human:7"
        a.set_destinations({"human:7": [{"member": "forum", "local_account_id": "501"}]})
        with app.app_context():
            a.export_outbox(0)
        assert gpost(gw, "/gateway/v1/actions", {"account_id": uid, "actions": [
            {"type": "post", "text": "my words", "crosspost_to": [{"member": "forum", "text": "my words for the forum"}]}]})[0] == 200
        with app.app_context():
            out = a.export_outbox(3)
        assert [(e.payload_type, e.target_member, e.payload["global_agent_id"], e.payload["target_account_id"],
                 e.payload["text_excerpt"]) for e in out] == [("crosspost.v1", "forum", "human:7", "501", "my words for the forum")]
    finally:
        app.config.pop("federation_adapter", None)


def test_people_are_outside_the_group_mechanisms_and_never_take_an_agent_identity(gw):
    from y_server.federation.adapter import YServerAdapter
    from y_server.federation.tables import FederationMembership, ensure_tables

    uid = enrol(gw)
    a = YServerAdapter("micro", 1, accounts={"g1": 1})
    with app.app_context():
        ensure_tables()
        assert a.agent_of(uid) == "human:7" and a.user_of("human:7") == uid
        assert a.agent_of(2) == "2"  # an unmapped agent keeps the old fallback
        db.session.add(FederationMembership(user_id=uid, global_agent_id="human:7", state="active", since_tick=0, reason="initial"))
        db.session.add(FederationMembership(user_id=1, global_agent_id="g1", state="active", since_tick=0, reason="initial"))
        db.session.commit()
        assert [s.global_agent_id for s in a.affective_report(0)] in ([], ["g1"])
        a.apply_attention(0, {"human:7": 2.0, "g1": 2.0})
        assert a.attention_multipliers() == {1: 2.0}
        db.session.query(User_mgmt).filter_by(id=uid).update({"left_on": 0})
        db.session.commit()
        assert "human:7" not in a.churned_agents(0)


def test_offline_applies_the_request_under_the_lock_and_refuses_when_the_server_runs(gw, tmp_path):
    lock = tmp_path / "x.lock"
    factory = lambda: HumanGateway(app)  # noqa: E731
    status, out = handle_offline(lock, "ensure", {"human_key": "off", "username": "off_h"}, factory, lambda: False)
    assert status == 200 and out["created"]
    uid = out["account_id"]
    status, out = handle_offline(lock, "actions", {"account_id": uid, "actions": [{"type": "post", "text": "from the shell"}]}, factory, lambda: False)
    assert status == 200 and out["ok"]
    assert handle_offline(lock, "actions", {"account_id": uid, "actions": [{"type": "post", "text": "x"}]}, factory, lambda: True)[0] == 409
    assert handle_offline(lock, "browse", {}, factory, lambda: False)[0] == 409
    assert handle_offline(lock, "ensure", [], factory, lambda: False)[0] == 400
    with app.app_context():
        assert [p.tweet for p in db.session.scalars(select(Post).filter_by(user_id=uid)).all()] == ["from the shell"]


def test_the_offline_lock_serialises_two_requests(tmp_path):
    from y_server.gateway.offline import handle_offline as run

    order, release = [], threading.Event()

    class Slow:
        def __init__(self, tag):
            self.tag = tag

    def factory_for(tag):
        def f():
            order.append(f"in:{tag}")
            if tag == "a":
                release.wait(2)
            order.append(f"out:{tag}")
            return type("G", (), {"state": lambda self, a: (200, {"tag": tag})})()
        return f

    lock = tmp_path / "l.lock"
    t = threading.Thread(target=lambda: run(lock, "state", {}, factory_for("a"), lambda: False))
    t.start()
    while "in:a" not in order:
        pass
    t2 = threading.Thread(target=lambda: run(lock, "state", {}, factory_for("b"), lambda: False))
    t2.start()
    release.set()
    t.join()
    t2.join()
    assert order == ["in:a", "out:a", "in:b", "out:b"]


def test_the_offline_script_answers_400_on_a_bad_request_and_prints_usage_without_arguments(tmp_path):
    root = os.path.dirname(os.path.dirname(__file__))
    cfg = tmp_path / "c.json"
    cfg.write_text("{}")
    p = subprocess.run([sys.executable, os.path.join(root, "run_offline_gateway.py"), str(cfg)], input="not json", capture_output=True,
                       text=True, timeout=60)
    assert p.returncode == 2 and json.loads(p.stdout)["status"] == 400
    p = subprocess.run([sys.executable, os.path.join(root, "run_offline_gateway.py")], capture_output=True, text=True, timeout=60)
    assert p.returncode == 2 and "Usage" in p.stdout
