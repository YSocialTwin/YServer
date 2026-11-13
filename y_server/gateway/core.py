"""The human gateway: one person, one account, the actions of the platform.

Every action goes through the SAME route of the server that the agents use (`/post`, `/comment`, `/reaction`,
`/follow`, `/share`), called in-process with the Flask test client, so that a person's post is stored, annotated and
marked for the federation exactly like an agent's. The gateway only checks that the account belongs to a person and
turns the request into the payload of the route. The same code serves the online routes (`/gateway/v1/...`, inside
the running server) and the offline script (`run_offline_gateway.py`)."""

from __future__ import annotations

import json
import re
from typing import Any

from sqlalchemy import select

MAX_ACTIONS = 20
MAX_TEXT = 2000
USERNAME = re.compile(r"^[A-Za-z0-9_]{1,15}$")
HUMAN_ID = re.compile(r"^human:[A-Za-z0-9_.:-]{1,70}$")
REACTIONS = ("like", "dislike")


class GatewayError(Exception):
    def __init__(self, status: int, code: str):
        super().__init__(code)
        self.status, self.code = status, code


class HumanGateway:
    def __init__(self, app):
        self.app = app

    # -- in-process calls of the routes of the server ---------------------------------------------
    def _call(self, method: str, path: str, payload: dict | None = None) -> dict:
        client = self.app.test_client()
        if method == "GET":
            resp = client.get(path)
        else:
            resp = client.post(path, data=json.dumps(payload or {}), content_type="application/json")
        try:
            body = json.loads(resp.get_data() or b"{}")
        except ValueError:
            body = {}
        if resp.status_code >= 400 and "status" not in body:
            body["status"] = resp.status_code
        return body

    def _round(self) -> int:
        body = self._call("GET", "/current_time")
        if "id" not in body:
            raise GatewayError(503, "no_round")
        return int(body["id"])

    # -- account ------------------------------------------------------------------------------------
    def _row(self, human_key=None, user_id=None):
        from y_server import db
        from .tables import GatewayHuman, ensure_tables

        ensure_tables()
        if human_key is not None:
            return db.session.get(GatewayHuman, human_key)
        return db.session.scalars(select(GatewayHuman).filter_by(user_id=int(user_id))).first()

    def ensure(self, human_key: str, username: Any, language: Any = None, human_id: Any = None) -> tuple[int, dict]:
        """Create the account of a person (idempotent); a name used by an account that is not a person's is refused."""
        from y_server import db
        from y_server.modals import User_mgmt
        from .tables import GatewayHuman

        if not isinstance(human_key, str) or not 1 <= len(human_key) <= 64:
            raise ValueError("human_key")
        if not isinstance(username, str) or not USERNAME.match(username):
            raise ValueError("username")
        if human_id is not None and (not isinstance(human_id, str) or not HUMAN_ID.match(human_id)):
            raise ValueError("human_id")
        with self.app.app_context():
            row = self._row(human_key)
            created = False
            if row is None:
                taken = db.session.scalars(select(User_mgmt).filter_by(username=username)).first()
                if taken is not None:
                    return 409, {"ok": False, "code": "username_taken"}
                reg = self._call("POST", "/register", {
                    "name": username, "email": f"{username}@human.local", "password": "", "leaning": "neutral", "age": 30,
                    "user_type": "human", "oe": "", "co": "", "ex": "", "ag": "", "ne": "", "language": str(language or "en"),
                    "education_level": "", "joined_on": self._round(), "round_actions": 0, "owner": "human", "gender": "",
                    "nationality": "", "toxicity": "no", "daily_activity_level": 1, "activity_profile": "", "profession": ""})
                if "id" not in reg:
                    return 500, {"ok": False, "code": "register_failed"}
                row = GatewayHuman(human_key=human_key, user_id=int(reg["id"]), human_id=human_id)
                db.session.add(row)
                created = True
            elif human_id is not None:
                if row.human_id not in (None, human_id):
                    return 409, {"ok": False, "code": "human_id_conflict"}
                row.human_id = human_id
            db.session.commit()
            user = db.session.get(User_mgmt, row.user_id)
            return 200, {"ok": True, "account_id": row.user_id, "username": user.username if user else username,
                         "human_id": row.human_id, "created": created}

    def state(self, account_id: Any) -> tuple[int, dict]:
        with self.app.app_context():
            row = self._row(user_id=self._account(account_id))
            if row is None:
                return 403, {"ok": False, "code": "not_a_human_account"}
            return 200, {"ok": True, "account_id": row.user_id, "human_id": row.human_id, "round": self._round()}

    @staticmethod
    def _account(account_id: Any) -> int:
        try:
            return int(account_id)
        except (TypeError, ValueError):
            raise ValueError("account_id") from None

    # -- actions --------------------------------------------------------------------------------------
    def actions(self, account_id: Any, actions: Any) -> tuple[int, dict]:
        if not isinstance(actions, list) or not 0 < len(actions) <= MAX_ACTIONS:
            raise ValueError("actions")
        uid = self._account(account_id)
        with self.app.app_context():
            if self._row(user_id=uid) is None:
                return 403, {"ok": False, "code": "not_a_human_account"}
            tid = self._round()
        results = []
        for act in actions:
            results.append(self._one(uid, tid, act))
        return 200, {"ok": all(r["ok"] for r in results), "results": results}

    def _one(self, uid: int, tid: int, act: Any) -> dict:
        kind = act.get("type") if isinstance(act, dict) else None
        try:
            payload, path = self._payload(uid, tid, kind, act)
        except ValueError as exc:
            return {"type": kind, "ok": False, "status": 400, "code": f"invalid_{exc}"}
        body = self._call("POST", path, payload)
        status = int(body.get("status", 200))
        out = {"type": kind, "ok": status == 200, "status": status}
        if out["ok"] and kind in ("post", "comment", "share"):
            with self.app.app_context():
                from y_server import db
                from y_server.modals import Post

                out["post_id"] = db.session.scalar(select(Post.id).filter_by(user_id=uid).order_by(Post.id.desc()).limit(1))
        return out

    @staticmethod
    def _text(act) -> str:
        text = act.get("text")
        if not isinstance(text, str) or not text.strip() or len(text) > MAX_TEXT:
            raise ValueError("text")
        return text.strip()

    @staticmethod
    def _id(act, key):
        v = act.get(key)
        if isinstance(v, bool) or not isinstance(v, int):
            raise ValueError(key)
        return v

    @staticmethod
    def _targets(act):
        targets = act.get("crosspost_to")
        if targets is None:
            return None
        if not isinstance(targets, list) or not targets or not all(
                isinstance(t, dict) and isinstance(t.get("member"), str) and t["member"] and isinstance(t.get("text"), str)
                for t in targets):
            raise ValueError("crosspost_to")
        return [{"member": t["member"], "text": t["text"]} for t in targets]

    def _payload(self, uid, tid, kind, act):
        base = {"user_id": uid, "tid": tid}
        if kind in ("post", "comment", "share"):
            text = self._text(act)
            tags = {"emotions": [], "hashtags": re.findall(r"#(\w+)", text), "mentions": re.findall(r"@(\w+)", text)}
            if kind == "post":
                topics = act.get("topics", [])
                if not isinstance(topics, list) or not all(isinstance(t, int) and not isinstance(t, bool) for t in topics):
                    raise ValueError("topics")
                payload, path = {**base, "tweet": text, "topics": topics, **tags}, "/post"
            else:
                payload, path = {**base, "post_id": self._id(act, "post_id"), "text": text, **tags}, f"/{kind if kind == 'share' else 'comment'}"
            targets = self._targets(act) if kind in ("post", "share") else None
            if targets:
                payload.update(crosspost=True, crosspost_to=targets)
            return payload, path
        if kind == "reaction":
            if act.get("reaction") not in REACTIONS:
                raise ValueError("reaction")
            return {**base, "post_id": self._id(act, "post_id"), "type": act["reaction"]}, "/reaction"
        if kind in ("follow", "unfollow"):
            return {**base, "target": self._id(act, "target"), "action": kind}, "/follow"
        raise ValueError("type")


def dispatch(gw: HumanGateway, method: str, parts: list, q: dict, body: dict) -> tuple[int, dict]:
    """Route one request of the gateway (shared by the online routes and the offline script)."""
    try:
        if parts == ["v1", "state"] and method == "GET":
            return gw.state(q.get("account_id") or body.get("account_id"))
        if parts == ["v1", "humans", "ensure"] and method == "POST":
            return gw.ensure(str(body.get("human_key") or ""), body.get("username"), body.get("language"), body.get("human_id"))
        if parts == ["v1", "actions"] and method == "POST":
            return gw.actions(body.get("account_id"), body.get("actions"))
        return 404, {"ok": False, "code": "not_found"}
    except ValueError as exc:
        return 400, {"ok": False, "code": "invalid_request", "field": str(exc)}
    except GatewayError as exc:
        return exc.status, {"ok": False, "code": exc.code}
