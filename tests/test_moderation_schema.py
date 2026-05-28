from sqlalchemy import create_engine, inspect, text

from y_server.schema_migrations import ensure_moderation_schema


def test_ensure_moderation_schema_adds_tables_and_post_column(tmp_path):
    db_path = tmp_path / "moderation_schema.db"
    engine = create_engine(f"sqlite:///{db_path}")

    with engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE user_mgmt (
                    id INTEGER PRIMARY KEY,
                    username VARCHAR(15) NOT NULL
                )
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE TABLE rounds (
                    id INTEGER PRIMARY KEY,
                    day INTEGER NOT NULL,
                    hour INTEGER NOT NULL
                )
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE TABLE post (
                    id INTEGER PRIMARY KEY,
                    tweet VARCHAR(500) NOT NULL,
                    round INTEGER NOT NULL,
                    user_id INTEGER NOT NULL
                )
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE TABLE agent_opinion (
                    id INTEGER PRIMARY KEY,
                    agent_id INTEGER NOT NULL,
                    tid INTEGER NOT NULL,
                    topic_id INTEGER NOT NULL,
                    opinion FLOAT NOT NULL
                )
                """
            )
        )

    ensure_moderation_schema(engine)

    inspector = inspect(engine)
    assert "sys_messages" in inspector.get_table_names()
    assert "reported" in inspector.get_table_names()
    assert "stress_reward" in inspector.get_table_names()
    assert "agent_custom_features" in inspector.get_table_names()
    post_columns = {column["name"] for column in inspector.get_columns("post")}
    assert "moderated" in post_columns
    assert "is_moderation_comment" in post_columns
    user_columns = {column["name"] for column in inspector.get_columns("user_mgmt")}
    assert "archetype" in user_columns
    assert "cover_image" in user_columns
    sys_message_columns = {column["name"] for column in inspector.get_columns("sys_messages")}
    assert "duration" in sys_message_columns
    assert "to_round" not in sys_message_columns
    opinion_columns = {column["name"] for column in inspector.get_columns("agent_opinion")}
    assert "stubborn" in opinion_columns
    stress_reward_columns = {
        column["name"] for column in inspector.get_columns("stress_reward")
    }
    assert {"id", "uid", "variable", "value", "type", "action", "tid"} <= stress_reward_columns


def test_ensure_moderation_schema_migrates_sys_messages_to_duration(tmp_path):
    db_path = tmp_path / "moderation_schema_legacy.db"
    engine = create_engine(f"sqlite:///{db_path}")

    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE user_mgmt (id INTEGER PRIMARY KEY, username VARCHAR(15) NOT NULL)"))
        conn.execute(text("CREATE TABLE rounds (id INTEGER PRIMARY KEY, day INTEGER NOT NULL, hour INTEGER NOT NULL)"))
        conn.execute(
            text(
                """
                CREATE TABLE sys_messages (
                    id INTEGER PRIMARY KEY,
                    type VARCHAR(50) NOT NULL,
                    to_uid INTEGER,
                    message TEXT NOT NULL,
                    from_round INTEGER,
                    to_round INTEGER
                )
                """
            )
        )
        conn.execute(
            text(
                """
                INSERT INTO sys_messages (id, type, to_uid, message, from_round, to_round)
                VALUES (1, 'moderation', 5, 'Test', 4, 7)
                """
            )
        )

    ensure_moderation_schema(engine)

    inspector = inspect(engine)
    sys_message_columns = {column["name"] for column in inspector.get_columns("sys_messages")}
    assert "duration" in sys_message_columns
    assert "to_round" not in sys_message_columns

    with engine.begin() as conn:
        row = conn.execute(text("SELECT from_round, duration FROM sys_messages WHERE id = 1")).first()

    assert row == (4, 3)


def test_ensure_moderation_schema_upgrades_legacy_stress_reward_table(tmp_path):
    db_path = tmp_path / "moderation_schema_stress_reward_legacy.db"
    engine = create_engine(f"sqlite:///{db_path}")

    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE user_mgmt (id INTEGER PRIMARY KEY, username VARCHAR(15) NOT NULL)"))
        conn.execute(text("CREATE TABLE rounds (id INTEGER PRIMARY KEY, day INTEGER NOT NULL, hour INTEGER NOT NULL)"))
        conn.execute(
            text(
                """
                CREATE TABLE stress_reward (
                    id VARCHAR(36) PRIMARY KEY,
                    uid INTEGER NOT NULL,
                    variable VARCHAR(16) NOT NULL CHECK (variable IN ('stress', 'reward')),
                    value FLOAT NOT NULL,
                    type VARCHAR(16) NOT NULL CHECK (type IN ('aggregate', 'variation')),
                    tid INTEGER NOT NULL
                )
                """
            )
        )
        conn.execute(
            text(
                """
                INSERT INTO stress_reward (id, uid, variable, value, type, tid)
                VALUES ('sr-1', 1, 'stress', -0.2, 'variation', 3)
                """
            )
        )

    ensure_moderation_schema(engine)

    inspector = inspect(engine)
    stress_reward_columns = {
        column["name"] for column in inspector.get_columns("stress_reward")
    }
    assert {"id", "uid", "variable", "value", "type", "action", "tid"} <= stress_reward_columns

    with engine.begin() as conn:
        row = conn.execute(
            text("SELECT variable, value, type, action, tid FROM stress_reward WHERE id = 'sr-1'")
        ).first()

    assert row == ("stress", -0.2, "variation", None, 3)
