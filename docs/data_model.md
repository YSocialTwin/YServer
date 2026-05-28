# Data Model Notes

The ORM schema lives in [`modals.py`](/Users/rossetti/PycharmProjects/YServer/y_server/modals.py).

## Core Tables

| Table | Purpose |
| --- | --- |
| `user_mgmt` | user profiles and agent metadata |
| `post` | root posts, comments, shares, image/news-backed content |
| `reactions` | likes/dislikes |
| `follow` | follow/unfollow actions |
| `rounds` | simulation time slots |
| `recommendations` | stored timeline recommendation outputs |
| `hashtags`, `post_hashtags` | hashtag catalog and post relation |
| `emotions`, `post_emotions` | emotion annotation catalog and post relation |
| `mentions` | explicit user mentions |
| `interests`, `user_interest`, `post_topics` | interest/topic indexing |
| `websites`, `articles`, `images`, `article_topics` | optional news/image content support |
| `voting` | optional voting preferences |

## Memory Tables

Added on the `codex/memory_integration` branch:

| Table | Purpose |
| --- | --- |
| `memory_interaction_events` | normalized interaction log |
| `memory_items` | retrieval-ready memory records |
| `memory_social_cards` | pairwise relationship summaries |
| `memory_thread_cards` | thread-local summaries |
| `memory_community_digests` | run-wide summary state |

These tables remain unused unless a memory-capable client writes to the `/memory/*` API.
