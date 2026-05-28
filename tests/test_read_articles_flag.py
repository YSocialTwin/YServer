from __future__ import annotations

import json

from y_server import app
from y_server.routes import content_management


class _FakeColumn:
    def __ge__(self, other):
        return ("ge", other)

    def __ne__(self, other):
        return ("ne", other)

    def in_(self, other):
        return ("in", tuple(other))


class _FakeQuery:
    def filter_by(self, **kwargs):
        return self

    def first(self):
        return type("User", (), {"id": 1, "leaning": "center"})()

    def all(self):
        return []

    def order_by(self, *args, **kwargs):
        return self


def test_read_treats_plural_articles_flag_as_article_mode(monkeypatch):
    captured = {}

    monkeypatch.setattr(
        content_management,
        "fetch_common_interest_posts",
        lambda **kwargs: captured.update(kwargs) or [],
    )
    monkeypatch.setattr(
        content_management,
        "User_mgmt",
        type("UserMgmt", (), {"query": _FakeQuery()}),
    )
    monkeypatch.setattr(content_management, "desc", lambda value: value)
    monkeypatch.setattr(
        content_management,
        "Rounds",
        type(
            "Rounds",
            (),
            {"id": _FakeColumn(), "query": type("Q", (), {"order_by": lambda self, *a, **k: self, "first": lambda self: type('Round', (), {'id': 10})()})()},
        ),
    )

    with app.test_request_context(
        "/read",
        method="POST",
        data=json.dumps(
            {
                "uid": 1,
                "limit": 5,
                "mode": "common_interests",
                "visibility_rounds": 36,
                "articles": True,
            }
        ),
    ):
        payload = json.loads(content_management.read())

    assert payload == []
    assert captured["articles"] is True
