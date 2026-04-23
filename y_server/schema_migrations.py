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


def _ensure_stress_reward_schema(engine, inspector) -> None:
    table_names = set(inspector.get_table_names())
    if "stress_reward" not in table_names:
        return

    columns = {column["name"] for column in inspector.get_columns("stress_reward")}
    needs_action_column = "action" not in columns
    dialect = engine.dialect.name
    if dialect == "sqlite":
        with engine.begin() as conn:
            create_sql_row = conn.execute(
                text(
                    "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'stress_reward'"
                )
            ).first()
        create_sql = str(create_sql_row[0] or "") if create_sql_row else ""
        expected_clause = "type = 'variation' AND value >= -1 AND value <= 1"
        if expected_clause in create_sql and not needs_action_column:
            return

        with engine.begin() as conn:
            conn.execute(
                text(
                    """
                    CREATE TABLE stress_reward__new (
                        id VARCHAR(36) PRIMARY KEY,
                        uid INTEGER NOT NULL REFERENCES user_mgmt(id),
                        variable VARCHAR(16) NOT NULL,
                        value FLOAT NOT NULL,
                        type VARCHAR(16) NOT NULL,
                        action VARCHAR(64),
                        tid INTEGER NOT NULL REFERENCES rounds(id),
                        CONSTRAINT ck_stress_reward_variable
                            CHECK (variable IN ('stress', 'reward')),
                        CONSTRAINT ck_stress_reward_type
                            CHECK (type IN ('aggregate', 'variation')),
                        CONSTRAINT ck_stress_reward_value
                            CHECK (
                                (type = 'aggregate' AND value >= 0 AND value <= 1)
                                OR (type = 'variation' AND value >= -1 AND value <= 1)
                            )
                    )
                    """
                )
            )
            conn.execute(
                text(
                    """
                    INSERT INTO stress_reward__new (id, uid, variable, value, type, action, tid)
                    SELECT
                        id,
                        uid,
                        variable,
                        value,
                        type,
                        NULL,
                        tid
                    FROM stress_reward
                    """
                )
            )
            conn.execute(text("DROP TABLE stress_reward"))
            conn.execute(text("ALTER TABLE stress_reward__new RENAME TO stress_reward"))
            conn.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS idx_stress_reward_uid ON stress_reward(uid)"
                )
            )
            conn.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS idx_stress_reward_tid ON stress_reward(tid)"
                )
            )
    else:
        with engine.begin() as conn:
            if needs_action_column:
                conn.execute(
                    text("ALTER TABLE stress_reward ADD COLUMN IF NOT EXISTS action VARCHAR(64)")
                )
            conn.execute(
                text("ALTER TABLE stress_reward DROP CONSTRAINT IF EXISTS ck_stress_reward_value")
            )
            conn.execute(
                text(
                    """
                    ALTER TABLE stress_reward
                    ADD CONSTRAINT ck_stress_reward_value
                    CHECK (
                        (type = 'aggregate' AND value >= 0 AND value <= 1)
                        OR (type = 'variation' AND value >= -1 AND value <= 1)
                    )
                    """
                )
            )


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
    if "user_mgmt" in table_names:
        user_columns = {column["name"] for column in inspector.get_columns("user_mgmt")}
        if "archetype" not in user_columns:
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE user_mgmt ADD COLUMN archetype VARCHAR(50)"))
        if "cover_image" not in user_columns:
            with engine.begin() as conn:
                conn.execute(
                    text("ALTER TABLE user_mgmt ADD COLUMN cover_image VARCHAR(400) DEFAULT ''")
                )

    SysMessage.__table__.create(bind=engine, checkfirst=True)
    Reported.__table__.create(bind=engine, checkfirst=True)
    StressReward.__table__.create(bind=engine, checkfirst=True)
    Agent_Custom_Feature.__table__.create(bind=engine, checkfirst=True)
    inspector = inspect(engine)
    _ensure_stress_reward_schema(engine, inspector)
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
