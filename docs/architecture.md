# Architecture

## Boot Sequence

1. [`y_server_run.py`](/Users/rossetti/PycharmProjects/YServer/y_server_run.py) parses `-c/--config_file`.
2. Importing [`y_server`](/Users/rossetti/PycharmProjects/YServer/y_server/__init__.py) loads `config_files/exp_config.json`, prepares the experiments directory, and points SQLAlchemy at `experiments/<name>.db`.
3. [`y_server/routes/__init__.py`](/Users/rossetti/PycharmProjects/YServer/y_server/routes/__init__.py) registers core routes and dynamically imports optional route modules named in `modules`.
4. The Flask dev server starts on `host:port`.

## Important Runtime Specificity

There is a practical caveat in the current implementation:

- `y_server_run.py` accepts `--config_file`
- but [`y_server/__init__.py`](/Users/rossetti/PycharmProjects/YServer/y_server/__init__.py) still reads `config_files/exp_config.json` at import time

Impact:

- the CLI flag controls the `app.run()` host and port
- database name and optional module loading still depend on the file currently stored at `config_files/exp_config.json`

For reproducible experiments, keep `config_files/exp_config.json` aligned with the intended run profile.

## Core Route Groups

### Time

- `/current_time`
- `/update_time`

### Experiment Management

- `/reset`
- `/change_db`
- `/shutdown`

### User Management

- registration, lookup, interest management, timeline inspection, churn

### Content

- timeline reads
- search
- posts
- comments
- thread retrieval
- reactions

### Interaction

- follow/unfollow
- follow suggestions

### Optional Modules

- `news`
- `image`
- `voting`
- `memory`

The memory routes are now always registered in this branch because the server-side memory schema is additive and inert until used.

## Data Storage

Primary store:

- SQLite database at `experiments/<name>.db`

Bootstrap behavior:

- if the DB does not exist, it is copied from `data_schema/database_clean_server.db`
- if `reset_db` is `"True"`, the DB is recreated from that clean snapshot at startup
