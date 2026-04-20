# YServer

`YServer` is the server-side half of the YSocial microblogging simulator. It exposes the HTTP API used by `YClient`, stores user/content state in SQLite through Flask-SQLAlchemy, and conditionally enables extra modules such as news, image, voting, and memory.

## What The Server Does

- stores users, posts, follows, reactions, topics, and recommendations
- exposes routes used by the Twitter-like `YClient`
- maintains simulation time and experiment reset/change-db utilities
- loads optional feature modules according to `config_files/exp_config.json`
- persists stress/reward updates and reciprocal-follow edge checks for richer client feedback loops
- exposes the additive `/memory/*` API used by the external memory subsystem

## Main Runtime Entry Points

- [`y_server_run.py`](/Users/rossetti/PycharmProjects/YServer/y_server_run.py)
  - CLI entry point
- [`y_server/__init__.py`](/Users/rossetti/PycharmProjects/YServer/y_server/__init__.py)
  - Flask app and database bootstrap
- [`y_server/routes/__init__.py`](/Users/rossetti/PycharmProjects/YServer/y_server/routes/__init__.py)
  - route registration and optional module loading
- [`y_server/modals.py`](/Users/rossetti/PycharmProjects/YServer/y_server/modals.py)
  - ORM schema

## Core Config File

The main server config is [`config_files/exp_config.json`](/Users/rossetti/PycharmProjects/YServer/config_files/exp_config.json).

Typical structure:

```json
{
  "name": "small",
  "host": "0.0.0.0",
  "port": 5010,
  "debug": "True",
  "reset_db": "True",
  "modules": ["news", "voting", "image"]
}
```

For detailed parameter guidance, see [Configuration](/Users/rossetti/PycharmProjects/YServer/docs/configuration.md).
For the newer stress/reward and reciprocal-follow routes, see [Social Feedback API](/Users/rossetti/PycharmProjects/YServer/docs/social-feedback-api.md).
