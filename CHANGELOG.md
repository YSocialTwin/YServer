# Changelog

All notable changes to this project are documented here. The format follows [Keep a Changelog](https://keepachangelog.com/).

## [Unreleased]

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
