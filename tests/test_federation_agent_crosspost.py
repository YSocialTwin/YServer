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
