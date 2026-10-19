"""Run the tests against a private, throw-away database.

``y_server`` reads its configuration (and opens its database) when it is imported,
so this must happen before any test module imports it. Without it the tests would
share, and pollute, the database named in ``config_files/exp_config.json``.
"""

import atexit
import json
import os
import shutil
import tempfile
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_TMP = Path(tempfile.mkdtemp(prefix="yserver_tests_"))
atexit.register(shutil.rmtree, _TMP, ignore_errors=True)

_config = json.loads((_ROOT / "config_files" / "exp_config.json").read_text(encoding="utf-8"))
_config.update(
    {
        "name": "pytest",
        "reset_db": "True",
        "database_uri": f"sqlite:///{_TMP / 'pytest_server.db'}",
    }
)
_config_path = _TMP / "exp_config.json"
_config_path.write_text(json.dumps(_config), encoding="utf-8")
os.environ["YSERVER_CONFIG"] = str(_config_path)
os.chdir(_ROOT)  # the server resolves data_schema/ and experiments/ relative to the repo


import pytest  # noqa: E402


@pytest.fixture(autouse=True)
def _empty_database():
    """Every test starts from, and leaves behind, empty tables of the test database."""

    def wipe():
        from y_server import app, db
        from y_server.routes.experiment_management import rebind_db

        with app.app_context():
            # some tests call /change_db: bring the app back to the test database
            rebind_db(_config["database_uri"])
            db.session.rollback()
            for table in reversed(db.metadata.sorted_tables):
                try:
                    db.session.execute(table.delete())
                    db.session.commit()  # per table: a missing table must not undo earlier deletes
                except Exception:
                    db.session.rollback()
            db.session.commit()
            db.session.remove()

    wipe()
    yield
    wipe()
