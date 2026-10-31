"""Tables of the federation inside the YServer database (all new, additive; created only when federation is on).

federation_membership: state of each local account as the coordinator told it (dormant, active, left).
federation_ref:        every content materialised from a cross-post (origin = federation) with its source.
federation_export:     posts handed to the bus, with the tick and the sequence number they were exported with, so that
                       exporting the same tick again gives the same messages (INV-05).
federation_state:      small key/value store (watermark of the posts that existed before the federation started)."""

from y_server import db


class FederationMembership(db.Model):
    __tablename__ = "federation_membership"

    user_id = db.Column(db.Integer, primary_key=True)
    global_agent_id = db.Column(db.String(64), nullable=False, unique=True)
    state = db.Column(db.String(10), nullable=False)
    since_tick = db.Column(db.Integer, nullable=False, default=0)
    reason = db.Column(db.String(16), nullable=False, default="initial")


class FederationRef(db.Model):
    __tablename__ = "federation_ref"

    local_kind = db.Column(db.String(16), primary_key=True)
    local_id = db.Column(db.Integer, primary_key=True)
    source_ref = db.Column(db.String(200), nullable=False)
    fed_msg_id = db.Column(db.String(200), nullable=False, unique=True)


class FederationExport(db.Model):
    __tablename__ = "federation_export"

    post_id = db.Column(db.Integer, primary_key=True)
    tick = db.Column(db.Integer, nullable=True)
    seq = db.Column(db.Integer, nullable=True)


class FederationAttention(db.Model):
    """Attention multiplier of the day for each account (F4.3); an account without a row has multiplier 1."""

    __tablename__ = "federation_attention"

    user_id = db.Column(db.Integer, primary_key=True)
    day = db.Column(db.Integer, nullable=False)
    multiplier = db.Column(db.Float, nullable=False)


class FederationExposure(db.Model):
    """exposure.v1 handed to the bus for a tick (F4.4b), fixed on the first export so that a retry sends the same messages."""

    __tablename__ = "federation_exposure_log"

    tick = db.Column(db.Integer, primary_key=True)
    seq = db.Column(db.Integer, primary_key=True)
    viewer_uid = db.Column(db.Integer, nullable=False)
    source_ref = db.Column(db.String(200), nullable=False)
    kind = db.Column(db.String(10), nullable=False)
    tie = db.Column(db.String(10), nullable=False)
    exact = db.Column(db.Boolean, nullable=False)


class FederationState(db.Model):
    __tablename__ = "federation_state"

    key = db.Column(db.String(32), primary_key=True)
    value = db.Column(db.String(64), nullable=False)


TABLES = (FederationMembership, FederationRef, FederationExport, FederationState, FederationAttention, FederationExposure)


def ensure_tables():
    """CREATE TABLE IF NOT EXISTS for the tables on the current database."""
    for model in TABLES:
        model.__table__.create(bind=db.engine, checkfirst=True)
