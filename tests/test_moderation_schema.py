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

    ensure_moderation_schema(engine)

    inspector = inspect(engine)
    assert "sys_messages" in inspector.get_table_names()
    assert "reported" in inspector.get_table_names()
    post_columns = {column["name"] for column in inspector.get_columns("post")}
    assert "moderated" in post_columns
    sys_message_columns = {column["name"] for column in inspector.get_columns("sys_messages")}
    assert "duration" in sys_message_columns
    assert "to_round" not in sys_message_columns


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
