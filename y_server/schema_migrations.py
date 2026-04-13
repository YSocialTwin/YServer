from __future__ import annotations

from sqlalchemy import inspect, text


def _ensure_sys_messages_duration_schema(engine, inspector) -> None:
    table_names = set(inspector.get_table_names())
    if "sys_messages" not in table_names:
        return

    columns = {column["name"] for column in inspector.get_columns("sys_messages")}
    has_duration = "duration" in columns
    has_to_round = "to_round" in columns

    if has_duration and not has_to_round:
        return

    dialect = engine.dialect.name
    with engine.begin() as conn:
        if dialect == "sqlite":
            conn.execute(
                text(
                    """
                    CREATE TABLE sys_messages__new (
                        id INTEGER PRIMARY KEY,
                        type VARCHAR(50) NOT NULL,
                        to_uid INTEGER REFERENCES user_mgmt(id),
                        message TEXT NOT NULL,
                        from_round INTEGER REFERENCES rounds(id),
                        duration INTEGER
                    )
                    """
                )
            )
            if has_to_round:
                conn.execute(
                    text(
                        """
                        INSERT INTO sys_messages__new (id, type, to_uid, message, from_round, duration)
                        SELECT
                            id,
                            type,
                            to_uid,
                            message,
                            from_round,
                            CASE
                                WHEN from_round IS NOT NULL AND to_round IS NOT NULL AND to_round >= from_round
                                    THEN to_round - from_round
                                ELSE NULL
                            END
                        FROM sys_messages
                        """
                    )
                )
            else:
                conn.execute(
                    text(
                        """
                        INSERT INTO sys_messages__new (id, type, to_uid, message, from_round, duration)
                        SELECT id, type, to_uid, message, from_round, duration
                        FROM sys_messages
                        """
                    )
                )
            conn.execute(text("DROP TABLE sys_messages"))
            conn.execute(text("ALTER TABLE sys_messages__new RENAME TO sys_messages"))
        else:
            if not has_duration:
                conn.execute(text("ALTER TABLE sys_messages ADD COLUMN duration INTEGER"))
            if has_to_round:
                conn.execute(
                    text(
                        """
                        UPDATE sys_messages
                        SET duration = CASE
                            WHEN duration IS NOT NULL THEN duration
                            WHEN from_round IS NOT NULL AND to_round IS NOT NULL AND to_round >= from_round
                                THEN to_round - from_round
                            ELSE NULL
                        END
                        """
                    )
                )
                conn.execute(text("ALTER TABLE sys_messages DROP COLUMN to_round"))


def ensure_moderation_schema(engine) -> None:
    """
    Ensure moderation-related additive schema exists on legacy experiment DBs.

    Existing SQLite databases are copied from prebuilt files, so additive columns
    and tables must be created explicitly for older experiments.
    """
    from y_server.modals import Agent_Custom_Feature, Reported, StressReward, SysMessage

    inspector = inspect(engine)
    table_names = set(inspector.get_table_names())

    if "post" in table_names:
        post_columns = {column["name"] for column in inspector.get_columns("post")}
        if "moderated" not in post_columns:
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE post ADD COLUMN moderated INTEGER DEFAULT 0"))
        if "is_moderation_comment" not in post_columns:
            with engine.begin() as conn:
                conn.execute(
                    text("ALTER TABLE post ADD COLUMN is_moderation_comment INTEGER DEFAULT 0")
                )

    SysMessage.__table__.create(bind=engine, checkfirst=True)
    Reported.__table__.create(bind=engine, checkfirst=True)
    StressReward.__table__.create(bind=engine, checkfirst=True)
    Agent_Custom_Feature.__table__.create(bind=engine, checkfirst=True)
    inspector = inspect(engine)
    table_names = set(inspector.get_table_names())
    if "agent_opinion" in table_names:
        opinion_columns = {column["name"] for column in inspector.get_columns("agent_opinion")}
        if "stubborn" not in opinion_columns:
            with engine.begin() as conn:
                conn.execute(
                    text("ALTER TABLE agent_opinion ADD COLUMN stubborn INTEGER DEFAULT 0")
                )
    inspector = inspect(engine)
    _ensure_sys_messages_duration_schema(engine, inspector)
