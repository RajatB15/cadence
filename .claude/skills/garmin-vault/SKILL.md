---
name: garmin-vault
description: Rules for working on Garmin sync, the raw-response vault, importer, or any new Garmin dataset/derived metric in Cadence. Use before touching app/backend/cadence_app/sync.py, garmin/, importer.py, or adding a dataset or metric.
---

Cadence keeps every Garmin response, then derives dashboards from the vault.

- Flow: Garmin API → `raw_responses` (compressed SQLite) + FIT ZIPs in `data/archive/garmin/fit/` (0600) → importer normalizes → analytics derive. Derived tables must be rebuildable from the vault with **zero API calls** ("Rebuild offline"); add/extend a test that asserts no client calls.
- New dataset: check the published Swagger (https://developer.garmin.com/gc-developer-program/personal/swagger-docs/) first; don't invent endpoints. Datasets returning 401/403 or empty probes become capability flags (unavailable), not failures. Store raw first, then normalize.
- Sync engine: 1 req/s throttle, back off on 429/Retry-After, window sizes are adaptive (400/500 on a range → halve and persist). Days older than 3 days are fetched once and never re-requested. Imports idempotent; sync resumable via persisted checkpoints.
- Garmin records win over demo data everywhere; never blend them. Demo data must stay labelled.
- Tests: use `tests/fake_garmin.py` / the demo connector. Never hit the real API or open `data/` from tests or exploration; never print tokens or personal response bodies.
- Schema change → Alembic migration in `cadence_app/migrations/versions/` plus package-data check in pyproject.
- Local-day semantics: preserve source timezone; normalize instants, bucket by local day.
- After the change run `cd app/backend && .venv/bin/pytest`, update plan.md "Current State", then use `ship-local`.
