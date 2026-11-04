"""INV-17 in YServer: accounts are reported by username and the global id comes from the coordinator, never from the local id."""

from __future__ import annotations

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
from y_server.federation.adapter import YServerAdapter  # noqa: E402
from y_server.modals import Post, User_mgmt  # noqa: E402
from tests.test_federation_bus import _post, client  # noqa: E402,F401  (fixtures)


@pytest.fixture()
def bound(client, tmp_path):
    a = YServerAdapter("micro", 1, bindings_file=str(tmp_path / "bindings.db"), export_policy="all")
    app.config["federation_adapter"] = a
    with app.app_context():
        yield a
    app.config.pop("federation_adapter", None)


def test_accounts_are_offered_by_username_once(bound):
    offered = bound.account_bindings()
    assert offered == [{"username": f"u{i}", "local_account_id": str(i)} for i in (1, 2, 3)]
    bound.bindings_reported(offered, [{"global_agent_id": "12", "local_account_id": "1"}, {"global_agent_id": "30", "local_account_id": "3"}])
    assert bound.account_bindings() == []
    with app.app_context():
        db.session.add(User_mgmt(id=4, username="u4", password="x", email="u4@x.org", joined_on=0))
        db.session.commit()
    offered = bound.account_bindings()
    assert offered == [{"username": "u4", "local_account_id": "4"}]
    bound.bindings_reported(offered, [])  # nobody expects "u4"
    assert bound.account_bindings() == []
    assert {"username": "u4", "local_account_id": "4"} in bound.account_bindings(retry=True)  # unmatched ones come back at day starts


def test_the_global_id_is_the_bound_one_and_never_the_local_id(bound):
    bound.bindings_reported(bound.account_bindings(), [{"global_agent_id": "12", "local_account_id": "1"}])
    assert bound.agent_of(1) == "12" and bound.user_of("12") == 1
    assert bound.agent_of(2) == "unbound:2"  # not known to the federation: no fallback to "2"
    assert bound.user_of("2") is None and bound.user_of("3") is None


def test_membership_reaches_the_account_of_the_bound_agent(bound):
    bound.bindings_reported(bound.account_bindings(), [{"global_agent_id": "12", "local_account_id": "1"}])
    bound.apply_membership([MembershipChange("12", "dormant", 0, "initial"), MembershipChange("3", "dormant", 0, "initial")])
    assert bound._active(1) is False and bound._active(3) is True  # "3" is nobody's id here: ignored, user 3 keeps acting


def test_only_bound_accounts_are_exported(client, bound):
    bound.bindings_reported(bound.account_bindings(), [{"global_agent_id": "12", "local_account_id": "1"}])
    bound.export_outbox(0)  # fixes the watermark
    _post(client, 1, "from a federation agent")
    _post(client, 2, "from an account the federation does not know")
    out = bound.export_outbox(3)
    assert [e.payload["global_agent_id"] for e in out] == ["12"]
    assert out[0].payload["text_excerpt"] == "from a federation agent"


def test_a_restart_keeps_the_bindings(client, tmp_path):
    path = str(tmp_path / "again.db")
    first = YServerAdapter("micro", 1, bindings_file=path)
    with app.app_context():
        first.bindings_reported(first.account_bindings(), [{"global_agent_id": "12", "local_account_id": "2"}])
        second = YServerAdapter("micro", 1, bindings_file=path)
        assert second.agent_of(2) == "12" and second.account_bindings() == []


def test_without_a_bindings_file_nothing_changes(client):
    a = YServerAdapter("micro", 1)
    with app.app_context():
        assert a.account_bindings() == [] and a.agent_of(2) == "2" and a.user_of("2") == 2


def test_provisioned_accounts_are_created_bound_and_offered_to_a_client_once(bound):
    done = bound.provision_accounts([{"global_agent_id": "40", "username": "newcomer", "interests": ["jazz"]},
                                     {"global_agent_id": "41", "username": "u1", "interests": []},  # already an account
                                     {"global_agent_id": "42", "username": "x" * 16, "interests": []}])  # not a username
    by = {d["global_agent_id"]: d["local_account_id"] for d in done}
    assert set(by) == {"40", "41"} and by["41"] == "1"
    assert bound.agent_of(int(by["40"])) == "40" and bound.user_of("40") == int(by["40"])
    assert [(p["username"], p["interests"]) for p in bound.provisioned_accounts()] == [("newcomer", ["jazz"])]
    assert all(o["username"] != "newcomer" for o in bound.account_bindings())  # known: never offered again
    import y_server.federation.visibility  # noqa: F401  (registers the routes)

    http = app.test_client()
    assert [a["username"] for a in http.get("/federation/provisioned").get_json()["accounts"]] == ["newcomer"]
    assert http.post("/federation/provisioned/adopted", json={"user_ids": [int(by["40"])]}).status_code == 200
    assert http.get("/federation/provisioned").get_json()["accounts"] == []
    # a client that restarts asks for all of them
    assert [x["username"] for x in http.get("/federation/provisioned?all=1").get_json()["accounts"]] == ["newcomer"]
    bound.mark_adopted([int(by["40"])])
    assert bound.provisioned_accounts() == []
