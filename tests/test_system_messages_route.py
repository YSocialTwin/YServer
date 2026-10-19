import json

import pytest

from y_server import app, db
from y_server.modals import Mentions, Rounds, SysMessage
from y_server.routes.content_management import (
    _filter_shadow_banned_post_ids,
    get_active_system_messages,
    read_mention,
)


@pytest.fixture()
def rows():
    """Add rows to the test database and remove them when the test ends."""
    added = []

    def add(*objs):
        with app.app_context():
            for obj in objs:
                db.session.merge(obj)
            db.session.commit()
        added.extend(objs)

    yield add
    with app.app_context():
        for obj in added:
            db.session.query(type(obj)).filter_by(id=obj.id).delete()
        db.session.commit()


def test_get_active_system_messages_filters_user_and_round(rows):
    rows(
        SysMessage(
            id=9001,
            type="moderation",
            to_uid=7,
            message="Start your post with MOD NOTICE.",
            from_round=2,
            duration=3,
        ),
        SysMessage(
            id=9002,
            type="warning",
            to_uid=7,
            message="Expired instruction.",
            from_round=0,
            duration=1,
        ),
        SysMessage(
            id=9003,
            type="moderation",
            to_uid=8,
            message="Other user.",
            from_round=2,
            duration=3,
        ),
    )

    with app.app_context():
        with app.test_request_context(
            "/get_active_system_messages",
            method="POST",
            data=json.dumps({"user_id": 7, "tid": 3}),
        ):
            payload = json.loads(get_active_system_messages())

    assert payload == [
        {
            "id": 9001,
            "type": "moderation",
            "message": "Start your post with MOD NOTICE.",
            "to_uid": 7,
            "from_round": 2,
            "duration": 3,
        }
    ]


def test_get_active_system_messages_returns_empty_list_when_none_match():
    with app.app_context():
        with app.test_request_context(
            "/get_active_system_messages",
            method="POST",
            data=json.dumps({"user_id": 987654, "tid": 3}),
        ):
            payload = json.loads(get_active_system_messages())

    assert payload == []


def test_shadow_ban_filter_falls_back_when_table_missing(monkeypatch):
    class _Inspector:
        def get_table_names(self):
            return []

    monkeypatch.setattr("y_server.routes.content_management.inspect", lambda *_args, **_kwargs: _Inspector())
    assert _filter_shadow_banned_post_ids([1, 2, 3], 5) == [1, 2, 3]


def test_read_mentions_skips_shadow_banned_posts(monkeypatch, rows):
    rows(
        Rounds(id=9020, day=1, hour=1),
        Mentions(id=9011, user_id=7, post_id=11, round=9018, answered=0),
        Mentions(id=9012, user_id=7, post_id=12, round=9018, answered=0),
    )
    monkeypatch.setattr(
        "y_server.routes.content_management._is_shadow_banned_post_hidden",
        lambda post_id, current_round_id: int(post_id) == 11,
    )

    with app.app_context():
        with app.test_request_context(
            "/read_mentions",
            method="POST",
            data=json.dumps({"uid": 7, "visibility_rounds": 5}),
        ):
            payload = json.loads(read_mention())

        answered = {
            m.post_id: m.answered
            for m in db.session.query(Mentions).filter(Mentions.id.in_([9011, 9012]))
        }

    assert payload == {"post_id": 12, "hashtags": []}
    assert answered == {11: 0, 12: 1}
