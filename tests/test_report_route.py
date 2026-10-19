import json
from types import SimpleNamespace

from y_server import app
from y_server.modals import Post, User_mgmt
from y_server.routes.content_management import report_post


class _Result:
    def __init__(self, obj):
        self._obj = obj

    def first(self):
        return self._obj


def _scalars(user, post):
    """``db.session.scalars`` stand-in: answers by the entity being selected."""

    def scalars(statement):
        entity = statement.column_descriptions[0]["entity"]
        return _Result(user if entity is User_mgmt else post if entity is Post else None)

    return scalars


def test_report_route_persists_report(monkeypatch):
    added = []

    with app.app_context():
        monkeypatch.setattr(
            "y_server.routes.content_management.db.session",
            SimpleNamespace(
                scalars=_scalars(SimpleNamespace(id=5), SimpleNamespace(id=9, user_id=14)),
                add=lambda obj: added.append(obj),
                commit=lambda: None,
                remove=lambda: None,
            ),
        )

        with app.test_request_context(
            "/report",
            method="POST",
            data=json.dumps({"user_id": 5, "post_id": 9, "type": "toxic", "tid": 7}),
        ):
            payload = json.loads(report_post())

    assert payload["status"] == 200
    assert len(added) == 1
    assert added[0].type == "toxic"
    assert added[0].to_uid == 14
    assert added[0].to_post == 9
    assert added[0].from_uid == 5
    assert added[0].tid == 7
