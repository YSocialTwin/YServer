from __future__ import annotations

import json
from types import SimpleNamespace

from y_server import app
from y_server.modals import Rounds, User_mgmt
from y_server.routes import content_management


class _Result:
    def __init__(self, rows):
        self._rows = rows

    def first(self):
        return self._rows[0] if self._rows else None

    def all(self):
        return list(self._rows)


def _scalars(statement):
    """``db.session.scalars`` stand-in: one user (no news pages) and a current round."""
    entity = statement.column_descriptions[0]["entity"]
    if entity is User_mgmt:
        # the user lookup (filter_by id) yields the user; the news pages lookup nothing
        is_page_lookup = "is_page" in str(statement.whereclause)
        return _Result([] if is_page_lookup else [SimpleNamespace(id=1, leaning="center")])
    if entity is Rounds:
        return _Result([SimpleNamespace(id=10)])
    return _Result([])


def test_read_treats_plural_articles_flag_as_article_mode(monkeypatch):
    captured = {}

    monkeypatch.setattr(
        content_management,
        "fetch_common_interest_posts",
        lambda **kwargs: captured.update(kwargs) or [],
    )
    monkeypatch.setattr(
        content_management.db,
        "session",
        SimpleNamespace(scalars=_scalars, remove=lambda: None),
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
