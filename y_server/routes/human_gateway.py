"""Online routes of the human gateway: `/gateway/v1/...` inside the running server, behind a per-run token.

Off unless the server configuration has `human_gateway.token` (then every route answers 404)."""

import hmac

from flask import jsonify, request
from y_server import app

TOKEN_HEADER = "X-YServer-Gateway-Token"


@app.route("/gateway/<path:rest>", methods=["GET", "POST"])
def human_gateway(rest):
    token = app.config.get("human_gateway_token")
    if not token:
        return jsonify({"ok": False, "code": "not_found"}), 404
    if not hmac.compare_digest(request.headers.get(TOKEN_HEADER, "").encode(), str(token).encode()):
        return jsonify({"ok": False, "code": "unauthorised"}), 401
    from y_server.gateway.core import HumanGateway, dispatch

    body = {}
    if request.method == "POST":
        body = request.get_json(silent=True)
        if not isinstance(body, dict) or request.content_length is not None and request.content_length > 64 * 1024:
            return jsonify({"ok": False, "code": "invalid_request"}), 400
    status, payload = dispatch(HumanGateway(app), request.method, [p for p in rest.split("/") if p], request.args.to_dict(), body)
    return jsonify(payload), status
