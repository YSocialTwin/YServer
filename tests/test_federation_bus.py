"""Bus and membership of YServer (F3.4a): export, ingest, membership, invisibility. No coordinator, no network."""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

pytest.importorskip("ysocial_federation", reason="the federation SDK is not installed")

from ysocial_federation.envelope import Envelope  # noqa: E402
from ysocial_federation.schemas import MembershipChange  # noqa: E402

from y_server import app, db  # noqa: E402
from y_server.federation import reset_federation  # noqa: E402
from y_server.federation.adapter import YServerAdapter  # noqa: E402
from y_server.federation import visibility  # noqa: E402
from y_server.modals import Follow, Post, Rounds, User_mgmt  # noqa: E402
from sqlalchemy import select  # noqa: E402


def _post_json(client, path, payload):
    return client.post(path, data=json.dumps(payload), content_type="application/json")


@pytest.fixture()
def client(tmp_path):
    exp_dir = tmp_path / "experiment"
    exp_dir.mkdir()
    db_path = exp_dir / "database_server.db"
    shutil.copyfile(ROOT / "data_schema" / "database_clean_server.db", db_path)
    app.config["TESTING"] = True
    c = app.test_client()
    assert _post_json(c, "/change_db", {"path": str(db_path)}).status_code == 200
    assert _post_json(c, "/reset", {}).status_code == 200
    with app.app_context():
        db.session.remove()
        for i in (1, 2, 3):
            db.session.add(User_mgmt(id=i, username=f"u{i}", password="x", email=f"u{i}@x.org", joined_on=0, language="it" if i == 2 else "en"))
        if db.session.scalars(select(Rounds)).first() is None:
            db.session.add(Rounds(day=0, hour=0))
        db.session.commit()
    yield c
    reset_federation()
    with app.app_context():
        db.session.remove()


@pytest.fixture()
def adapter(client):
    a = YServerAdapter("micro", 1, accounts={"g1": 1, "g2": 2, "g3": 3})
    app.config["federation_adapter"] = a
    with app.app_context():
        yield a
    app.config.pop("federation_adapter", None)


def _post(client, uid, text, crosspost=None):
    body = {"user_id": uid, "tweet": text, "emotions": [], "hashtags": [], "mentions": [], "topics": [], "tid": 1}
    if crosspost is not None:
        body["crosspost"] = crosspost
    assert _post_json(client, "/post", body).status_code == 200


def _crosspost(seq, target, text="hello", tick=4):
    return Envelope.create(1, "forum", "micro", tick, seq, "crosspost.v1",
                           {"global_agent_id": "g9", "source_ref": f"ysocial://1/forum/post/{seq}", "kind": "post",
                            "text_excerpt": text, "image_ref": None, "topics": [], "lang": "en", "target_account_id": target})


def test_the_post_flag_is_ignored_without_a_federation(client):
    _post(client, 1, "a", crosspost=True)
    with app.app_context():
        assert app.config.get("federation_adapter") is None
        assert db.session.scalar(select(Post.id)) is not None


def test_export_only_marked_posts_in_a_stable_order(client, adapter):
    adapter.export_outbox(0)  # fixes the watermark
    _post(client, 1, "not marked")
    _post(client, 2, "marked two", crosspost=True)
    _post(client, 1, "marked one", crosspost=True)
    out = adapter.export_outbox(3)
    assert [(e.seq, e.payload["text_excerpt"], e.payload["global_agent_id"]) for e in out] == [(0, "marked two", "g2"), (1, "marked one", "g1")]
    assert out[0].payload["lang"] == "it" and out[0].payload["source_ref"].startswith("ysocial://1/micro/post/")
    assert out[0].target_member == "coordinator" and out[0].tick_emitted == 3
    again = adapter.export_outbox(3)  # a retry of the same tick: the same messages, same ids
    assert [e.fed_msg_id for e in again] == [e.fed_msg_id for e in out]
    assert adapter.export_outbox(4) == []  # exported once


def test_export_all_policy_skips_old_comments_dormant_and_federated_posts(client):
    a = YServerAdapter("micro", 1, accounts={"g1": 1, "g2": 2, "g3": 3}, export_policy="all")
    app.config["federation_adapter"] = a
    try:
        with app.app_context():
            db.session.add(Post(tweet="old", round=1, user_id=1, comment_to=-1, thread_id=1))
            db.session.commit()
            a.export_outbox(0)
        _post(client, 1, "new root")
        _post(client, 3, "dormant author")
        with app.app_context():
            db.session.add(Post(tweet="a reply", round=1, user_id=1, comment_to=1, thread_id=1))
            db.session.commit()
            a.apply_membership([MembershipChange("g3", "dormant", 0, "initial")])
            assert a.ingest_inbox(2, [_crosspost(0, 2)]).materialized == 1
            out = a.export_outbox(5)
            assert [e.payload["text_excerpt"] for e in out] == ["new root"]  # no old post, reply, dormant or federated post
    finally:
        app.config.pop("federation_adapter", None)


def test_ingest_materialises_once_with_a_reference(client, adapter):
    from y_server.federation.tables import FederationRef

    inbox = [_crosspost(0, 1, "from the forum"), _crosspost(1, 2, "second")]
    r1 = adapter.ingest_inbox(5, inbox)
    assert (r1.materialized, r1.duplicates, r1.skipped_total) == (2, 0, 0)
    r2 = adapter.ingest_inbox(5, inbox)  # INV-05: the same messages again change nothing
    assert (r2.materialized, r2.duplicates) == (0, 2)
    posts = db.session.scalars(select(Post).order_by(Post.id)).all()
    assert [(p.tweet, p.user_id, p.comment_to, p.thread_id == p.id) for p in posts] == [("from the forum", 1, -1, True), ("second", 2, -1, True)]
    refs = db.session.scalars(select(FederationRef).order_by(FederationRef.local_id)).all()
    assert [(r.local_kind, r.source_ref, r.fed_msg_id) for r in refs] == [
        ("post", "ysocial://1/forum/post/0", inbox[0].fed_msg_id), ("post", "ysocial://1/forum/post/1", inbox[1].fed_msg_id)]


def test_ingest_skips_unknown_and_dormant_accounts_and_unsupported_messages(client, adapter):
    adapter.apply_membership([MembershipChange("g2", "dormant", 0, "initial")])
    content = Envelope.create(1, "forum", "micro", 4, 9, "content.v1",
                              {"global_agent_id": "g1", "source_ref": "ysocial://1/forum/post/9", "kind": "post", "text_excerpt": "x",
                               "image_ref": None, "topics": [], "lang": "en"})
    r = adapter.ingest_inbox(5, [_crosspost(0, 2), _crosspost(1, 99), content, _crosspost(2, 3)])
    assert r.materialized == 1 and r.skipped == {"skipped_ineligible": 2, "skipped_unsupported": 1}


def test_membership_is_stored_and_updated(client, adapter):
    from y_server.federation.tables import FederationMembership

    adapter.apply_membership([MembershipChange("g1", "dormant", 0, "initial"), MembershipChange("g2", "active", 0, "initial"),
                              MembershipChange("zzz", "active", 0, "initial")])
    adapter.apply_membership([MembershipChange("g1", "active", 24, "join")])
    rows = {r.user_id: (r.state, r.since_tick, r.reason) for r in db.session.scalars(select(FederationMembership)).all()}
    assert rows == {1: ("active", 24, "join"), 2: ("active", 0, "initial")}
    adapter.apply_membership([MembershipChange("g2", "left", 48, "churn")])
    assert visibility.inactive_user_ids() == [2]


def test_dormant_accounts_are_invisible_and_clients_get_their_ids(client, adapter):
    visibility.install(app)
    try:
        _post(client, 1, "visible")
        _post(client, 2, "hidden")
        def authors_read():
            res = json.loads(_post_json(client, "/read", {"limit": 10, "mode": "rchrono_popularity", "visibility_rounds": 100,
                                                          "uid": 3, "followers_ratio": 1}).data)
            flat = [x for part in res for x in (part if isinstance(part, list) else [part])]
            return {db.session.get(Post, int(i)).user_id for i in flat}

        assert authors_read() == {1, 2}  # nothing hidden yet
        adapter.apply_membership([MembershipChange("g2", "dormant", 0, "initial")])
        assert json.loads(client.get("/federation/inactive_users").data) == {"inactive": [2]}
        assert authors_read() == {1}
        sug = json.loads(_post_json(client, "/follow_suggestions", {"user_id": 3, "n_neighbors": 5, "leaning_biased": 0, "mode": "random"}).data)
        assert "2" not in {str(k) for k in sug}
    finally:
        visibility.uninstall()


def test_adapter_conformance_suite(client):
    from ysocial_federation.testing.conformance import ConformanceCase, run_all

    def sample_inbox(a, tick):
        return [Envelope.create(1, "forum", "micro", tick - 1, seq, "crosspost.v1",
                                {"global_agent_id": "1", "source_ref": f"ysocial://1/forum/post/{tick}-{seq}", "kind": "post",
                                 "text_excerpt": "x", "image_ref": None, "topics": [], "lang": "en", "target_account_id": 1})
                for seq in range(3)]

    def factory():
        a = YServerAdapter("micro", 1)
        app.config["federation_adapter"] = a
        return a

    case = ConformanceCase(factory, (0, 0), lambda r: (r[0], r[1] + 1) if r[1] < 23 else (r[0] + 1, 0), "micro", 1,
                           agent_ids=["1", "2"], sample_inbox=sample_inbox)
    with app.app_context():
        assert "ingest_is_idempotent" in run_all(case)
    app.config.pop("federation_adapter", None)
