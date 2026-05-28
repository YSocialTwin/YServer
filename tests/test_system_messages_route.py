import json
from types import SimpleNamespace

from y_server import app
from y_server.modals import SysMessage
from y_server.routes.content_management import (
    _filter_shadow_banned_post_ids,
    get_active_system_messages,
    read_mention,
)


class _FakeSysMessageQuery:
    def __init__(self, messages):
        self._messages = list(messages)
        self._filtered = list(messages)

    def filter_by(self, **kwargs):
        to_uid = kwargs.get("to_uid")
        self._filtered = [msg for msg in self._messages if msg.to_uid == to_uid]
        return self

    def all(self):
        return list(self._filtered)


def test_get_active_system_messages_filters_user_and_round(monkeypatch):
    messages = [
        SimpleNamespace(
            id=1,
            type="moderation",
            to_uid=7,
            message="Start your post with MOD NOTICE.",
            from_round=2,
            duration=3,
        ),
        SimpleNamespace(
            id=2,
            type="warning",
            to_uid=7,
            message="Expired instruction.",
            from_round=0,
            duration=1,
        ),
        SimpleNamespace(
            id=3,
            type="moderation",
            to_uid=8,
            message="Other user.",
            from_round=2,
            duration=3,
        ),
    ]

    with app.app_context():
        monkeypatch.setattr(SysMessage, "query", _FakeSysMessageQuery(messages))
        with app.test_request_context(
            "/get_active_system_messages",
            method="POST",
            data=json.dumps({"user_id": 7, "tid": 3}),
        ):
            payload = json.loads(get_active_system_messages())

    assert payload == [
        {
            "id": 1,
            "type": "moderation",
            "message": "Start your post with MOD NOTICE.",
            "to_uid": 7,
            "from_round": 2,
            "duration": 3,
        }
    ]


def test_get_active_system_messages_returns_empty_list_when_none_match(monkeypatch):
    with app.app_context():
        monkeypatch.setattr(SysMessage, "query", _FakeSysMessageQuery([]))
        with app.test_request_context(
            "/get_active_system_messages",
            method="POST",
            data=json.dumps({"user_id": 7, "tid": 3}),
        ):
            payload = json.loads(get_active_system_messages())

    assert payload == []


def test_shadow_ban_filter_falls_back_when_table_missing(monkeypatch):
    class _Inspector:
        def get_table_names(self):
            return []

    monkeypatch.setattr("y_server.routes.content_management.inspect", lambda *_args, **_kwargs: _Inspector())
    assert _filter_shadow_banned_post_ids([1, 2, 3], 5) == [1, 2, 3]


def test_read_mentions_skips_shadow_banned_posts(monkeypatch):
    mentions = [
        SimpleNamespace(post_id=11, answered=0),
        SimpleNamespace(post_id=12, answered=0),
    ]

    class _FakeMentionQuery:
        def filter(self, *_args, **_kwargs):
            return self

        def order_by(self, *_args, **_kwargs):
            return self

        def all(self):
            return mentions

    class _FakeRoundsQuery:
        def order_by(self, *_args, **_kwargs):
            return self

        def first(self):
            return SimpleNamespace(id=20)

    class _FakeHashtagQuery:
        def filter(self, *_args, **_kwargs):
            return self

        def all(self):
            return []

    commit_calls = []

    with app.app_context():
        monkeypatch.setattr("y_server.routes.content_management.Mentions.query", _FakeMentionQuery())
        monkeypatch.setattr("y_server.routes.content_management.Rounds.query", _FakeRoundsQuery())
        monkeypatch.setattr(
            "y_server.routes.content_management._is_shadow_banned_post_hidden",
            lambda post_id, current_round_id: int(post_id) == 11,
        )
        monkeypatch.setattr(
            "y_server.routes.content_management.db.session.query",
            lambda *_args, **_kwargs: _FakeHashtagQuery(),
        )
        monkeypatch.setattr(
            "y_server.routes.content_management.db.session.commit",
            lambda: commit_calls.append("commit"),
        )
        with app.test_request_context(
            "/read_mentions",
            method="POST",
            data=json.dumps({"uid": 7, "visibility_rounds": 5}),
        ):
            payload = json.loads(read_mention())

    assert payload == {"post_id": 12, "hashtags": []}
    assert mentions[0].answered == 0
    assert mentions[1].answered == 1
    assert commit_calls == ["commit"]
