"""The human gateway of the microblogging Standard runtime, as YSocial's World Simulation talks to it.

The gateway is a set of routes of the server itself; its token is the ``human_gateway.token`` option of the server
configuration. When the server is stopped the person acts through the runtime script (``run_offline_gateway.py``).
"""

from __future__ import annotations

from y_web.sdk import HumanGatewayTraits


def ensure_body(key, username, human_id, language):
    return {
        "human_key": key,
        "username": username,
        "language": language,
        "human_id": human_id,
    }


def actions_request(account_id, username, key, actions):
    acct = int(account_id) if str(account_id).isdigit() else account_id
    return "/gateway/v1/actions", {"account_id": acct, "actions": actions}


def offline_ensure(paths, body):
    return [str(paths.server_config)], {"op": "ensure", "body": body}


def offline_actions(paths, path, body):
    return [str(paths.server_config)], {"op": "actions", "body": body}


def post(text, targets):
    return {"type": "post", "text": text, "crosspost_to": targets}


def share(post_id, text, targets):
    return {"type": "share", "post_id": post_id, "text": text, "crosspost_to": targets}


def build_action(text, targets, post_id=None, community=None):
    return share(post_id, text, targets) if post_id else post(text, targets)


HUMAN_GATEWAY = HumanGatewayTraits(
    repo="YServer",
    token_header="X-YServer-Gateway-Token",
    ensure_path="/gateway/v1/humans/ensure",
    actions_path="/gateway/v1/actions",
    token_in_server_config=True,
    ensure_body=ensure_body,
    actions_request=actions_request,
    offline_ensure=offline_ensure,
    offline_actions=offline_actions,
    build_action=build_action,
)
