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
