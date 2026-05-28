# Social Feedback API

Recent YServer updates added two related API surfaces that support richer client-side behavior without breaking the client/server contract:

- stress/reward persistence and aggregate reconstruction
- follow-back and unfollow-back edge validation

The server owns the database and stores the resulting state. It does not perform any LLM-based interpretation of comments, posts, or user profiles.

## Stress/Reward Endpoints

The stress/reward pipeline is enabled only when the server configuration exposes `stress_reward.enabled` or the equivalent legacy flat flag.

The server persists rows in the `stress_reward` table using:

- `variable`: `stress` or `reward`
- `type`: `aggregate` or `variation`
- `action`: optional action label for variation rows
- `tid`: round id

### `POST /set_stress_reward_variations`

Accepts one or more variation updates computed by the client. The server inserts the variation rows and maintains same-round aggregate checkpoints for the target user.

The route expects the client to have already computed the deltas. That is why annotation and interpretation remain client-side.

### `POST|GET /get_stress_reward`

Returns the current aggregate stress/reward state for a user at a given round. The server reconstructs the value from:

- the latest aggregate checkpoint not later than the requested round
- later variation rows in the selected window

The implementation also includes same-round variations that occur after an aggregate checkpoint, which matters for clients that refresh state multiple times in the same round.

## Reciprocal Follow Support

The reciprocal follow/unfollow feature depends on a lightweight server-side graph check.

### `POST /check_follow_relationship`

Given `follower_id` and `user_id`, the route returns whether the latest effective edge state currently represents a follow from the first user to the second.

Clients use this route before attempting:

- a follow-back when the reverse edge must not already exist
- an unfollow-back when the reverse edge must already exist

That keeps the edge validation server-side while leaving the actual decision logic in the client.

## Related Lifecycle Endpoint

### `POST /churn`

The churn route now supports two usage modes:

- batch churn by count, for older flows
- explicit `user_id` plus `left_on`, for client-side churn decisions such as the stress/reward pipeline

This lets the client decide *whether* a user should leave while the server remains the only component that mutates `user_mgmt.left_on`.

## Schema Notes

The additive migration logic ensures that older experiment databases are upgraded in place. In particular, the current schema guarantees:

- presence of the `stress_reward` table on migrated databases
- presence of the `action` column on legacy `stress_reward` tables
- value constraints that allow signed variation rows while keeping aggregate rows in `[0, 1]`

The reset and change-database flows also rerun the additive schema setup so the social feedback endpoints stay available when switching experiments.
