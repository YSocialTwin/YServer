# Changelog

All notable changes to this project are documented here. The format follows [Keep a Changelog](https://keepachangelog.com/).

## [Unreleased]

### Added
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
