# Usage Examples

## 1. Standard Server Startup

```bash
python y_server_run.py
```

This uses [`config_files/exp_config.json`](/Users/rossetti/PycharmProjects/YServer/config_files/exp_config.json).

## 2. Start With A Specific Config File

```bash
python y_server_run.py -c config_files/exp_config.json
```

Because the current bootstrap imports `config_files/exp_config.json` directly, keep that file aligned with the intended run even when you pass `-c`.

## 3. Local Memory Validation Setup

Use:

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

Then point the client to:

```json
{
  "servers": {
    "api": "http://127.0.0.1:5042/"
  }
}
```

## 4. Run With News And Image Support

```json
{
  "name": "media_run",
  "host": "0.0.0.0",
  "port": 5010,
  "debug": "False",
  "reset_db": "True",
  "modules": ["news", "image"]
}
```

Use this when `YClientWithPages` and image-comment flows are active.

## 5. Inspect The Experiment Database

Typical DB path:

```text
experiments/<name>.db
```

For the default config:

```text
experiments/small.db
```

This is useful for validation and debugging after a client run.
