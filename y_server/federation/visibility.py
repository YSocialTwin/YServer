"""Invisibility of the accounts that are not active on this platform (guide 4.10.1) and the client-facing list.

Active only when the federation is on (install() is called by init_federation): for the requests that build
recommendations, search results, mention lists and follow suggestions, posts, users and follows of dormant or left
accounts are left out of every query. Nothing changes without the federation (INV-01)."""

from flask import has_request_context, jsonify, request
from sqlalchemy import event, select
from sqlalchemy.orm import Session, with_loader_criteria

HIDING_PATHS = ("/read", "/search", "/read_mentions", "/follow_suggestions")
_installed = False


def inactive_user_ids():
    """Ids of the accounts whose state is dormant or left."""
    from y_server import db
    from .tables import FederationMembership, ensure_tables

    ensure_tables()
    rows = db.session.scalars(
        select(FederationMembership.user_id).where(FederationMembership.state != "active")
        .execution_options(federation_skip=True)).all()
    return sorted(rows)


def _hide(state):
    if not (has_request_context() and request.path in HIDING_PATHS):
        return
    if not state.is_select or state.execution_options.get("federation_skip"):
        return
    if "federation.hidden" not in request.environ:  # computed once per request
        request.environ["federation.hidden"] = inactive_user_ids()
    hidden = request.environ["federation.hidden"]
    if not hidden:
        return
    from y_server.modals import Follow, Post, User_mgmt

    state.statement = state.statement.options(
        with_loader_criteria(Post, Post.user_id.not_in(hidden), include_aliases=True),
        with_loader_criteria(User_mgmt, User_mgmt.id.not_in(hidden), include_aliases=True),
        with_loader_criteria(Follow, Follow.user_id.not_in(hidden) & Follow.follower_id.not_in(hidden), include_aliases=True),
    )


def _register_route(app):
    if "federation_inactive_users" not in app.view_functions:
        @app.route("/federation/inactive_users", methods=["GET"], endpoint="federation_inactive_users")
        def _inactive_users():
            return jsonify({"inactive": inactive_user_ids()})

    if "federation_attention" not in app.view_functions:
        @app.route("/federation/attention", methods=["GET"], endpoint="federation_attention")
        def _attention():
            adapter = app.config.get("federation_adapter")
            multipliers = adapter.attention_multipliers() if adapter is not None else {}
            return jsonify({"multipliers": {str(k): v for k, v in multipliers.items()}})


def install(app):
    """Register the listener (the route that tells the clients which accounts must not act exists from the import)."""
    global _installed
    if not _installed:
        event.listen(Session, "do_orm_execute", _hide)
        _installed = True



def uninstall():
    """Remove the listener (tests)."""
    global _installed
    if _installed:
        event.remove(Session, "do_orm_execute", _hide)
        _installed = False


def _boot():
    from y_server import app

    _register_route(app)


_boot()  # this module is imported only when the federation is on: the new route appears only then
