"""Offline entry of a person: one JSON request on stdin, one JSON answer on stdout.

Usage: python run_offline_gateway.py <exp_config.json>      (stdin: {"op": "ensure"|"state"|"actions", "body": {...}})

Works only while the server of the experiment is stopped (see ``y_server/gateway/offline.py``): the same operations as
the online gateway, applied to the database of the experiment under a file lock. Answer: the body of the gateway plus
``status`` (409 ``server_running`` when the server is up)."""

import json
import os
import sys
from pathlib import Path


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 1:
        print(__doc__)
        return 2
    config_file = Path(argv[0]).resolve()
    try:
        config = json.loads(config_file.read_text())
        request = json.loads(sys.stdin.read() or "{}")
        assert isinstance(request, dict)
    except (OSError, ValueError, AssertionError):
        print(json.dumps({"ok": False, "status": 400, "code": "invalid_request"}))
        return 2
    os.environ["YSERVER_CONFIG"] = str(config_file)
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from y_server.gateway.offline import handle_offline, server_running

    def factory():
        from y_server import app
        from y_server.gateway.core import HumanGateway

        return HumanGateway(app)

    status, body = handle_offline(
        config_file.with_suffix(".human.lock"), str(request.get("op", "")), request.get("body") or {}, factory,
        lambda: server_running(config.get("host"), config.get("port", 5010)))
    print(json.dumps({**body, "status": status}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
