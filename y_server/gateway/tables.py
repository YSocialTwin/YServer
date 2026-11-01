"""Table of the human gateway (additive): the accounts the gateway created for people."""

from y_server import db


class GatewayHuman(db.Model):
    """One person on this platform: `human_key` is the key YWeb gives (stable per person and experiment); `human_id`
    is the federation identity ("human:<id>") once the person is enrolled in a World Simulation."""

    __tablename__ = "gateway_human"

    human_key = db.Column(db.String(64), primary_key=True)
    user_id = db.Column(db.Integer, nullable=False, unique=True)
    human_id = db.Column(db.String(80), nullable=True)


def ensure_tables():
    GatewayHuman.__table__.create(bind=db.engine, checkfirst=True)


def human_users():
    """{local user id: federation identity or None} of the accounts created by the gateway (empty when there are none).

    Never touches the session of the caller when the table does not exist (no rollback of its pending changes)."""
    from sqlalchemy import inspect, select

    if not inspect(db.engine).has_table(GatewayHuman.__tablename__):
        return {}
    return {r.user_id: r.human_id for r in db.session.scalars(select(GatewayHuman)).all()}
