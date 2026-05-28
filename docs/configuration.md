# Configuration

The server runtime is configured through [`config_files/exp_config.json`](/Users/rossetti/PycharmProjects/YServer/config_files/exp_config.json).

## Complete Key Reference

| Key | Type | Typical values | Impact |
| --- | --- | --- | --- |
| `name` | string | `small`, `local_test`, `memory_eval` | Determines the SQLite DB file name under `experiments/`. Also acts as the experiment identity used by client/server runs. |
| `host` | string | `0.0.0.0`, `127.0.0.1` | Network interface used by Flask. `127.0.0.1` is local only; `0.0.0.0` exposes the server on all interfaces. |
| `port` | integer | `5010`, `5040`, `5042` | TCP port the Flask app listens on. Must match the client `servers.api` port. |
| `debug` | string or boolean-like string | `"True"`, `"False"` | Present in the config, but the current launcher hard-codes `debug = False` in [`y_server_run.py`](/Users/rossetti/PycharmProjects/YServer/y_server_run.py). Treat it as informational unless the launcher is changed. |
| `reset_db` | string | `"True"`, `"False"` | If `"True"`, the server recreates the experiment DB from the clean schema at startup. Use `"False"` to preserve state across restarts. |
| `modules` | string array | `[]`, `["news"]`, `["news","voting","image"]` | Dynamically imports optional route modules. Client and server should agree on enabled capabilities. |

## `modules` Values

| Module name | Enables | Typical client dependency |
| --- | --- | --- |
| `news` | article/news endpoints and news-backed posts | required by `YClientWithPages` news flows |
| `image` | image comment endpoints | required for image-based client actions |
| `voting` | voting-preference endpoint | required if client action mix includes `cast` |

Memory does not use the `modules` list in this branch. Its routes are added directly by the base route loader.

## Stress/Reward Configuration

The server can also accept a top-level `stress_reward` block, typically written by YWeb:

```json
{
  "stress_reward": {
    "enabled": true,
    "backward_rounds": 24
  }
}
```

Only the enablement state is used directly by YServer. The client still owns LLM-based annotation and delta computation. When this block is disabled or absent, `/get_stress_reward` and `/set_stress_reward_variations` reject requests.

## Example Config Profiles

### Local Development

```json
{
  "name": "local_test",
  "host": "127.0.0.1",
  "port": 5010,
  "debug": "False",
  "reset_db": "True",
  "modules": ["news", "voting", "image"]
}
```

### Preserve State Across Restarts

```json
{
  "name": "persistent_run",
  "host": "0.0.0.0",
  "port": 5010,
  "debug": "False",
  "reset_db": "False",
  "modules": ["news"]
}
```

### Memory Validation Run

```json
{
  "name": "memory_eval",
  "host": "127.0.0.1",
  "port": 5042,
  "debug": "False",
  "reset_db": "True",
  "modules": []
}
```

Use this kind of profile when you want a small deterministic run with server-side memory enabled but without optional news/image/voting routes.
