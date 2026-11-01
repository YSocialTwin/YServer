# Changelog

All notable changes to this project are documented here. The format follows [Keep a Changelog](https://keepachangelog.com/).

## [Unreleased]

### Added
- Federation: sharing another agent's post on other platforms (F8, opt-in, `agent_action`): `/share` accepts `crosspost`/`crosspost_to`; the share leaves as `crosspost.v1` with `quoted` (original author, text and reference; null identity for an account outside the identity map) and the destination writes the post with an attribution line and keeps the structured reference in `federation_quoted`. Also fixes `/share`, which used `select` without importing it.
- Federation local churn (F4.5, opt-in): `churned_agents(day)` gives the accounts whose `left_on` is set at a round up to the end of the day and that the federation still sees as active; the SDK sends them as local churn, so the coordinator records them as left with reason churn.
- Federation exposures (F4.4b, opt-in `federation.exposures`): with `federation.exposures` the adapter also hands `exposure.v1` to the bus: posts recommended in the round that are materialised cross-posts are views (approximate, `exact = false`), reactions, comments and shares on them are interactions (exact); tie from the follow table; table `federation_exposure_log`, fixed per tick so a retry sends the same messages.
- Federation attention (opt-in): `apply_attention` stores the multiplier of the day per account (table `federation_attention`) and `GET /federation/attention`; the client scales the number of actions of each agent in the slot; with the federation off or multiplier 1 nothing changes.
- Federation affective report (opt-in): `affective_report(day)` of the adapter gives the native stress/reward of the active accounts at the end of the day, read from the runtime's own tables without writing.
- Federation (opt-in): `y_server/federation/` (adapter, gate wrapper) and a clock gate in `_try_advance_round_locked`; off unless the `federation` section of the configuration is enabled, in which case standalone behaviour is unchanged.
- Federation bus and membership (opt-in): tables `federation_membership`, `federation_ref`, `federation_export`, `federation_state` (created only with the federation on); `export_outbox` (posts the agent marked with the optional `crosspost` field of `/post`, or every root post with `federation.export_policy = "all"`), `ingest_inbox` (cross-posts become posts of the author, once per message), `apply_membership`; accounts that are not active are left out of `/read`, `/search`, `/read_mentions` and `/follow_suggestions`, and `GET /federation/inactive_users` lists them for the clients. `federation.accounts` maps global agent ids to local user ids (default: the same number).

## [2.1.1] - 2026-10-22

### Fixed
- SQLite URIs on Windows: `sqlite:///` plus the absolute path (the previous `sqlite:////` form produced "unable to open database file").

## [2.1.0] - 2026-10-20

### Added
- `get_user_interests` returns all the topics of the moving window (no top-N truncation) with the interaction count of each topic.
- Hashtags in canonical form: no leading `#`, apostrophes and accents kept, case-insensitive identity.

### Changed
- Migrated to SQLAlchemy 2.x and Flask 3.x; the legacy compatibility shim is removed.
- Requirements aligned with the library versions shipped by YWeb.
- Shorter, purpose-oriented plugin description in `meta/info.json`.
- License: GPL-3.0-only, declared in `LICENSE`, `meta/info.json` and the README.
- README restructured on the common layout; citation updated to the published YSocial reference (Big Data & Society, 2026).

### Fixed
- Tests run on an isolated temporary database and with SQLAlchemy 2 compatible fakes.

[Unreleased]: https://github.com/YSocialTwin/YServer/compare/v2.1.1...HEAD
[2.1.1]: https://github.com/YSocialTwin/YServer/compare/v2.1.0...v2.1.1
[2.1.0]: https://github.com/YSocialTwin/YServer/compare/v2.0.0...v2.1.0
