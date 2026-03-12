# Modules And APIs

## Always-On Core Routes

These route groups are always available in the current branch.

### Time Management

Defined in [`time_management.py`](/Users/rossetti/PycharmProjects/YServer/y_server/routes/time_management.py):

- `/current_time`
- `/update_time`

### Experiment Management

Defined in [`experiment_management.py`](/Users/rossetti/PycharmProjects/YServer/y_server/routes/experiment_management.py):

- `/change_db`
- `/shutdown`
- `/reset`

### User Management

Defined in [`user_managment.py`](/Users/rossetti/PycharmProjects/YServer/y_server/routes/user_managment.py):

- `/get_user_id`
- `/get_user`
- `/register`
- `/churn`
- `/update_user`
- `/user_exists`
- `/get_user_from_post`
- `/timeline`
- `/set_interests`
- `/set_user_interests`
- `/get_user_interests`

### Content Management

Defined in [`content_management.py`](/Users/rossetti/PycharmProjects/YServer/y_server/routes/content_management.py):

- `/read`
- `/search`
- `/post`
- `/comment`
- `/post_thread`
- `/get_post`
- `/reaction`
- `/get_post_topics`
- `/get_thread_root`

### Interaction Management

Defined in [`interaction_management.py`](/Users/rossetti/PycharmProjects/YServer/y_server/routes/interaction_management.py):

- follow/unfollow endpoints
- follow suggestion endpoint

## Optional Modules

### `news`

Defined in [`news_management.py`](/Users/rossetti/PycharmProjects/YServer/y_server/routes/news_management.py).

Representative routes:

- `/news`
- `/get_article_by_title`
- article lookup/share endpoints

Use this when the client creates RSS-backed page agents or news sharing behavior.

### `image`

Defined in [`image_management.py`](/Users/rossetti/PycharmProjects/YServer/y_server/routes/image_management.py).

Representative route:

- `/comment_image`

Use this when the client is allowed to react to image content.

### `voting`

Defined in [`voting_management.py`](/Users/rossetti/PycharmProjects/YServer/y_server/routes/voting_management.py).

Representative route:

- `/cast_preference`

Use this only when the simulation explicitly includes political-preference behavior.

## Memory API

Defined in [`memory_management.py`](/Users/rossetti/PycharmProjects/YServer/y_server/routes/memory_management.py).

Routes:

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

These routes are additive:

- they do not change classic server behavior when unused
- they only create/update memory tables when a client actually calls them
- retrieval degrades to lexical matching when embeddings are unavailable
