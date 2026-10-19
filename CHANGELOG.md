# Changelog

All notable changes to this project are documented here. The format follows [Keep a Changelog](https://keepachangelog.com/).

## [Unreleased]

Changes made since the last published state of `main`, newest first:

- get_user_interests: return all topics in the moving window (no top-N truncation)
- get_user_interests: return per-topic interaction count
- Hashtags: canonical form without '#', apostrophes and accents kept in the tag, case-insensitive identity
- i18n: shorter, purpose-oriented plugin descriptions
- Align requirements with the library versions shipped by YWeb
- refactor: remove SA2 legacy shim (_ensure_flask_sqlalchemy_legacy_compat)
- update .gitignore
- update deps
- deps: migrate to SQLAlchemy 2.x / Flask 3.x
