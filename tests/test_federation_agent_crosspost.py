"""F6.2: cross-post as an agent action (crosspost.mode = agent_action) on YServer."""

import json

import pytest

from tests.test_federation_bus import _post_json, client  # noqa: F401  (fixture)
from y_server import app, db
from y_server.federation.adapter import YServerAdapter

pytest.importorskip("ysocial_federation")

DEST = {"g1": [{"member": "forum", "local_account_id": "201"}, {"member": "dating", "local_account_id": "301"}],
        "g2": [{"member": "forum", "local_account_id": "202"}]}


@pytest.fixture()
def agent(client):  # noqa: F811
    a = YServerAdapter("micro", 1, accounts={"g1": 1, "g2": 2, "g3": 3}, crosspost_mode="agent_action")
    app.config["federation_adapter"] = a
    a.set_destinations(DEST)
    with app.app_context():
        yield a
    app.config.pop("federation_adapter", None)


def _post(client, uid, text, to=None, crosspost=True):  # noqa: F811
    body = {"user_id": uid, "tweet": text, "emotions": [], "hashtags": [], "mentions": [], "topics": [], "tid": 1}
    if crosspost:
        body["crosspost"] = True
    if to is not None:
        body["crosspost_to"] = to
    assert _post_json(client, "/post", body).status_code == 200


def test_the_agent_sends_a_crosspost_with_its_own_text_to_each_chosen_destination(client, agent):  # noqa: F811
    agent.export_outbox(0)
    _post(client, 1, "original", to=[{"member": "forum", "text": "Title\nbody"}, {"member": "dating", "text": "hi there"}])
    out = agent.export_outbox(3)
    assert [(e.payload_type, e.target_member, e.payload["target_account_id"], e.payload["text_excerpt"]) for e in out] == [
        ("crosspost.v1", "dating", "301", "hi there"), ("crosspost.v1", "forum", "201", "Title\nbody")]
    assert [e.seq for e in out] == [1, 2]  # seq 0 belongs to the post itself: no content.v1 is sent for it
    assert all(e.source_member == "micro" and e.tick_emitted == 3 for e in out)
    assert out[0].payload["global_agent_id"] == "g1" and out[0].payload["source_ref"].startswith("ysocial://1/micro/post/")
    assert [e.fed_msg_id for e in agent.export_outbox(3)] == [e.fed_msg_id for e in out]  # a retry sends the same messages
    assert agent.export_outbox(4) == []


def test_a_retry_keeps_the_account_even_if_the_destinations_changed(client, agent):  # noqa: F811
    agent.export_outbox(0)
    _post(client, 1, "original", to=[{"member": "forum", "text": "x"}])
    first = agent.export_outbox(3)
    agent.set_destinations({})
    assert [e.to_dict() for e in agent.export_outbox(3)] == [e.to_dict() for e in first]


def test_a_destination_without_an_active_account_is_dropped(client, agent):  # noqa: F811
    agent.export_outbox(0)
    _post(client, 2, "two", to=[{"member": "forum", "text": "ok"}, {"member": "dating", "text": "no account"}])
    out = agent.export_outbox(3)
    assert [(e.target_member, e.payload["target_account_id"]) for e in out] == [("forum", "202")]


def test_a_post_without_targets_in_agent_action_mode_sends_nothing_but_content_policy_all_still_does(client, agent):  # noqa: F811
    agent.export_outbox(0)
    _post(client, 1, "marked but nowhere", to=[])
    assert agent.export_outbox(3) != [] and agent.export_outbox(3)[0].payload_type == "content.v1"


def test_exposures_after_crossposts_never_reuse_a_sequence_number(client):  # noqa: F811
    a = YServerAdapter("micro", 1, accounts={"g1": 1, "g2": 2, "g3": 3}, crosspost_mode="agent_action", export_policy="all", emit_exposures=True)
    app.config["federation_adapter"] = a
    a.set_destinations(DEST)
    try:
        with app.app_context():
            a.export_outbox(0)
            _post(client, 1, "with xp", to=[{"member": "forum", "text": "t"}])
            _post(client, 2, "plain", crosspost=False)
            out = a.export_outbox(3)
            assert len({e.seq for e in out}) == len(out)
            assert sorted((e.payload_type, e.target_member) for e in out) == [("content.v1", "coordinator"), ("crosspost.v1", "forum")]
    finally:
        app.config.pop("federation_adapter", None)


def test_targets_are_ignored_in_coordinator_rule_mode(client):  # noqa: F811
    a = YServerAdapter("micro", 1, accounts={"g1": 1})
    app.config["federation_adapter"] = a
    try:
        with app.app_context():
            a.export_outbox(0)
            _post(client, 1, "x", to=[{"member": "forum", "text": "t"}])
            out = a.export_outbox(3)
            assert [(e.payload_type, e.target_member) for e in out] == [("content.v1", "coordinator")]
    finally:
        app.config.pop("federation_adapter", None)


def test_the_destinations_route(client, agent):  # noqa: F811
    assert json.loads(client.get("/federation/destinations?user_id=1").data) == {"destinations": ["dating", "forum"]}
    assert json.loads(client.get("/federation/destinations?user_id=3").data) == {"destinations": []}
    assert client.get("/federation/destinations?user_id=x").status_code == 422


def test_an_unknown_mode_is_refused():
    with pytest.raises(ValueError):
        YServerAdapter("micro", 1, crosspost_mode="nope")


# -- F8: sharing the content of another agent ------------------------------------------------------------
def _share(client, uid, post_id, text, to=None):  # noqa: F811
    body = {"user_id": uid, "post_id": post_id, "text": text, "emotions": [], "hashtags": [], "mentions": [], "tid": 1}
    if to is not None:
        body.update(crosspost=True, crosspost_to=to)
    assert _post_json(client, "/share", body).status_code == 200


def _last_post_id():
    from y_server.modals import Post

    return db.session.scalars(db.select(Post).order_by(Post.id.desc())).first().id


def test_a_share_with_targets_leaves_as_a_crosspost_quoting_the_original_author(client, agent):  # noqa: F811
    agent.export_outbox(0)
    _post(client, 2, "words of the second agent", crosspost=False)
    original = _last_post_id()
    _share(client, 1, original, "so true", to=[{"member": "forum", "text": "so true"}])
    out = agent.export_outbox(3)
    assert [(e.payload_type, e.target_member, e.payload["global_agent_id"], e.payload["text_excerpt"]) for e in out] == [
        ("crosspost.v1", "forum", "g1", "so true")]
    q = out[0].payload["quoted"]
    assert q["global_agent_id"] == "g2" and q["member"] == "micro" and q["text_excerpt"] == "words of the second agent"
    assert q["source_ref"] == f"ysocial://1/micro/post/{original}"


def test_a_share_without_targets_and_an_unmarked_share_never_leave(client, agent):  # noqa: F811
    agent.export_outbox(0)
    _post(client, 2, "words", crosspost=False)
    _share(client, 1, _last_post_id(), "plain share")
    assert agent.export_outbox(3) == []


def test_an_author_outside_the_federation_is_quoted_as_anonymous(client, agent):  # noqa: F811
    agent.export_outbox(0)
    _post(client, 3, "from a non member", crosspost=False)
    agent._by_user.pop(3, None)  # account 3 is not in the identity map
    agent._accounts.pop("g3", None)
    _share(client, 1, _last_post_id(), "look", to=[{"member": "forum", "text": "look"}])
    q = agent.export_outbox(3)[0].payload["quoted"]
    assert q["global_agent_id"] is None and q["source_ref"] is None and q["text_excerpt"] == "from a non member"


def test_the_destination_writes_the_post_with_the_attribution_and_keeps_the_reference(client, agent):  # noqa: F811
    from y_server.modals import Post
    from y_server.federation.tables import FederationQuoted
    from ysocial_federation.envelope import Envelope

    q = {"author_name": "ann", "global_agent_id": "gx", "member": "forum", "source_ref": "ysocial://1/forum/post/4",
         "text_excerpt": "original words"}
    env = Envelope.create(1, "forum", "micro", 2, 0, "crosspost.v1",
                          {"global_agent_id": "g1", "source_ref": "ysocial://1/forum/post/7", "kind": "post", "text_excerpt": "agreed",
                           "image_ref": None, "topics": [], "lang": "en", "target_account_id": 1, "quoted": q})
    agent.ingest_inbox(3, [env])
    post = db.session.scalars(db.select(Post).order_by(Post.id.desc())).first()
    assert post.tweet == "agreed\n↪ ann @ forum: «original words»"
    row = db.session.get(FederationQuoted, post.id)
    assert (row.author_name, row.global_agent_id, row.member, row.source_ref) == ("ann", "gx", "forum", "ysocial://1/forum/post/4")


# -- topic migration -------------------------------------------------------------------------------------
def _xpost_env(topics, fed_id_seq=0, text="agreed"):
    from ysocial_federation.envelope import Envelope

    return Envelope.create(1, "forum", "micro", 2, fed_id_seq, "crosspost.v1",
                           {"global_agent_id": "g1", "source_ref": f"ysocial://1/forum/post/{70 + fed_id_seq}", "kind": "post", "text_excerpt": text,
                            "image_ref": None, "topics": topics, "lang": "en", "target_account_id": 1})


def test_topics_travel_with_the_content_and_missing_ones_are_created_once(client, agent):  # noqa: F811
    from y_server.modals import Interests, Post, Post_topics
    from y_server.federation.tables import FederationTopic

    existing = Interests(interest="Music")
    db.session.add(existing)
    db.session.commit()
    agent.ingest_inbox(3, [_xpost_env(["music", "Climate", "climate", "  "])])
    post = db.session.scalars(db.select(Post).order_by(Post.id.desc())).first()
    names = sorted(i.interest for i in db.session.scalars(
        db.select(Interests).join(Post_topics, Post_topics.topic_id == Interests.iid).where(Post_topics.post_id == post.id)).all())
    assert names == ["Climate", "Music"]  # matched case-insensitively, one created, duplicates ignored
    assert [(t.name, t.source_member, t.created_tick) for t in db.session.scalars(db.select(FederationTopic)).all()] == [("Climate", "forum", 3)]
    assert db.session.scalar(db.select(db.func.count()).select_from(Interests).where(db.func.lower(Interests.interest) == "climate")) == 1
    agent.ingest_inbox(3, [_xpost_env(["Climate"], 1)])  # a second post reuses the topic
    assert db.session.scalar(db.select(db.func.count()).select_from(FederationTopic)) == 1


def test_a_redelivered_message_adds_no_topic_twice(client, agent):  # noqa: F811
    from y_server.modals import Post_topics

    env = _xpost_env(["Gardening"])
    agent.ingest_inbox(3, [env])
    before = db.session.scalar(db.select(db.func.count()).select_from(Post_topics))
    agent.ingest_inbox(4, [env])
    assert db.session.scalar(db.select(db.func.count()).select_from(Post_topics)) == before


def test_a_share_leaves_with_the_topics_of_the_original_post(client, agent):  # noqa: F811
    from y_server.modals import Interests, Post_topics

    agent.export_outbox(0)
    i = Interests(interest="Space")
    db.session.add(i)
    db.session.commit()
    _post(client, 2, "rockets", crosspost=False)
    original = _last_post_id()
    db.session.add(Post_topics(post_id=original, topic_id=i.iid))
    db.session.commit()
    _share(client, 1, original, "wow", to=[{"member": "forum", "text": "wow"}])
    assert agent.export_outbox(3)[0].payload["topics"] == ["Space"]
