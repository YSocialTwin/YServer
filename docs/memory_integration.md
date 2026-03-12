# YServer Memory Integration

This branch adds the server-side memory API needed by the shared `y_memory_subsystem` package, aligning `YServer` with the memory contract already implemented in `YServerReddit`.

The port is structural, not behavioral. Existing Twitter-like routes such as `/post`, `/comment`, `/read`, `/search`, `/news`, `/share`, `/comment_image`, and `/cast_preference` keep their current behavior. Memory becomes active only when a client explicitly calls the new `/memory/*` endpoints.

## What Was Added

- `y_server/modals.py`
  - new run-scoped memory ORM models:
    - `MemoryInteractionEvent`
    - `MemorySocialCard`
    - `MemoryThreadCard`
    - `MemoryCommunityDigest`
    - `MemoryItem`
- `y_server/memory_embedding.py`
  - optional Ollama-backed embedding helper
  - graceful degradation to lexical retrieval when embeddings are unavailable
- `y_server/routes/memory_management.py`
  - dedicated additive route module for the memory API
  - imported from `y_server/routes/__init__.py`
- `tests/test_memory_management.py`
  - Flask-level tests covering the new API surface

## Endpoint Surface

The following endpoints are now available:

- `/memory/reset`
- `/memory/event`
- `/memory/social/upsert`
- `/memory/thread/upsert`
- `/memory/community/get`
- `/memory/community/update`
- `/memory/item/upsert`
- `/memory/search`
- `/memory/get_context`
- `/memory/events_recent`

These endpoints follow the same run-scoped contract used by the Reddit server integration so that `YClient` and `YClientReddit` can both target the same external memory package.

## YServer-Specific Adaptation

`YServer` targets a Twitter-like simulation, not a Reddit-like forum. The port therefore preserves the memory model while keeping the current server semantics:

- thread memory uses the existing `thread_id` / root-post convention already present in `Post`
- no Reddit-only post fields were introduced
- no existing timeline, recommendation, or interaction route was rewritten to write memory automatically
- no sentiment/toxicity pipeline was added as part of this change

The result is a passive memory capability that can support the client-side adapter without introducing regressions into the existing simulation flow.

## Retrieval Behavior

`/memory/search` supports:

- run scoping through `run_id`
- agent scoping through `agent_user_id`
- optional filtering by `other_user_id`
- optional filtering by `thread_root_id`
- lexical fallback scoring
- semantic scoring when embeddings are available
- retrieval diagnostics in `retrieval_meta`

If the embedding backend is unavailable, retrieval degrades to lexical matching instead of failing.

## Schema And Safety

- memory tables are created lazily via `db.create_all()` when a memory route is first used
- memory data is fully isolated by `run_id`
- prompt-scaffold-like payloads are sanitized before storage
- failures in the embedding backend do not block writes or reads

## Tests

Run the focused server memory test suite with:

```bash
PYTHONPATH=. uv run --python 3.12 --with flask==2.1.2 --with Werkzeug==2.1.2 --with Jinja2==3.1.2 --with itsdangerous==2.1.2 --with click==8.1.3 --with Flask-Login==0.6.1 --with Flask-SQLAlchemy==2.5.1 --with SQLAlchemy==1.4.37 --with numpy --with pytest python -m pytest -q tests/test_memory_management.py
```

Covered scenarios:

- event writes mirrored into the searchable memory stream
- social/thread card upserts and prompt context assembly
- lexical search fallback
- community digest reads/writes
- run-scoped reset behavior
