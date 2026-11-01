"""Federation hooks of YServer (opt-in, guide 4.8).

With the `federation` section of the configuration absent or `enabled: false` nothing here is imported beyond this
file, `_federation_gate` stays None and the server behaves exactly as without federation (INV-01). With it enabled the
SDK `ysocial_federation` must be importable."""

import logging
import os

log = logging.getLogger("y_server.federation")


def init_federation(config):
    """Create the gate from config["federation"] and install it in the time management routes.

    Returns the installed gate, or None when the federation is off."""
    section = (config or {}).get("federation") or {}
    if not section.get("enabled"):
        return None
    from .adapter import YServerAdapter
    from .gate import SafeGate
    from ysocial_federation.gate import FederationGate

    from y_server import app
    from y_server.routes import time_management as tm

    section = dict(section)
    section.setdefault("exp_id", os.path.basename(str(config.get("name", ""))) or None)
    adapter = YServerAdapter(section["member"], int(section.get("federation_id", 1)),
                             accounts=section.get("accounts"), export_policy=section.get("export_policy", "marked"),
                             emit_exposures=bool(section.get("exposures", False)),
                             crosspost_mode=section.get("crosspost_mode", "coordinator_rule"),
                             topic_migration=bool(section.get("topic_migration", True)),
                             bindings_file=section.get("bindings_file"),
                             crosspost_content=(section.get("crosspost_content") or None))
    from . import visibility
    gate = SafeGate(FederationGate(adapter, section))
    with app.app_context():
        with tm._SYNC_LOCK:
            current = tm._get_current_round_locked()
            gate.start((current.day, current.hour))
    tm._federation_gate = gate
    app.config["federation_adapter"] = adapter
    with app.app_context():
        from .tables import ensure_tables

        ensure_tables()
    visibility.install(app)
    return gate


def reset_federation():
    """Switch the federation off again (used by tests)."""
    from y_server.routes import time_management as tm

    tm._federation_gate = None
    tm._federation_pending = False
    from y_server import app

    app.config.pop("federation_adapter", None)
    from . import visibility

    visibility.uninstall()
