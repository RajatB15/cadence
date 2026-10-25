# Cadence

Single-user, local-first health and training coach: Garmin data in a local SQLite vault → analytics → React web app (also served to an iPhone). See [README.md](README.md) for user-facing docs.

## Rules

- Read [plan.md](plan.md) before planning or implementing project changes. It is the source of truth for scope, stack, roadmap, and acceptance criteria; update its checklist (and the "Current State" entry) when milestones are verified.
- Build the local-first web experience first and implement LLM integration last. There is no macOS app or packaging: Cadence is a server plus the web app, and text recognition is always Tesseract.
- Do not assume Garmin API capabilities are verified. Body-composition values are formula estimates and are never presented as measured.
- Store everything, surface what matters: keep every imported response in the vault (never drop data at import), but product pages show curated, meaningful views and derived insights rather than raw field dumps. Raw records stay inspectable through the Vault data explorer.
- Local Garmin credentials are in `.secrets/garmin.env`. Load them directly in the backend process when needed; never print, copy into prompts, put in frontend bundles, log, or commit them. Do not request the key again while this file is available. Never Read or cat this file; only reference it from code.
- Credential expiry metadata lives alongside the key. Implement the renewal reminder specified in plan.md; never infer expiry from the token format.
- Do not make authenticated network requests merely to inspect credentials. Verify official endpoint documentation before using the key; never invent endpoints.
- `data/` (SQLite vault, FIT archive, VAPID key) holds personal health data. Never read them into the conversation beyond aggregate counts/schema, never commit them, never put real records in tests or logs. Tests use synthetic fixtures (`app/backend/tests/fake_garmin.py`, demo connector).
- Analytics are transparent and cautious: show sample sizes and uncertainty, enforce minimum-data rules, no causal or medical claims. Keep pure algorithms (`analytics/athlete.py`, `performance.py`, `recovery.py`, `plan.py`, `score.py`) separate from loading/assembly (`insights.py`: `context()` loads, `assemble()` is pure and is what tests use) and wording (`notes.py`). Every method cites its source in the module docstring and the Coach page's "How the coach works".
- Distinguish missing data from zero. UI changes need empty, loading, error and unsupported-capability states, and must work at desktop and phone widths.
- Food data (the food library crawl) lives only in the private `food-data` submodule (separate private repo `cadence-food-data`); never copy it, a catalogue built from it, or other third-party food datasets into this repo, which is public. Built-in dishes are estimates calculated from web recipes, never presented as measured.
- Never claim data is encrypted unless it is. The local service binds to loopback; the phone share server (port 8766) is read-only apart from `/api/push/*`.

## Commands

| Task | Command |
| --- | --- |
| Backend tests | `cd app/backend && .venv/bin/pytest` (single: `.venv/bin/pytest tests/test_api.py -k name`) |
| Frontend tests / types | `cd app/web && npm test` / `npm run typecheck` |
| Backend dev server (:8765) | `cd app/backend && .venv/bin/cadence-app` |
| Frontend dev server (:5173) | `cd app/web && npm run dev` |
| Build frontend | `npm --prefix app/web run build` (typechecks first) |
| Login service | `scripts/cadence-service.sh install\|restart\|status\|logs\|uninstall` |

Run focused tests for changed behavior. The running LaunchAgent serves the built `app/web/dist` and the installed backend: after frontend changes rebuild, after backend changes restart the service (see the `ship-local` skill).

## Layout

- `app/backend/cadence_app/` — FastAPI app: `server.py`/`main.py` (routes), `sync.py` + `garmin/` (vault sync engine), `importer.py`, `models.py` + `migrations/` (Alembic: schema changes need a migration), `analytics/`, `wellbeing_store.py` (daily self-report: feel, soreness, pain, illness, life load; only ever pulls the plan towards less), `nutrients.py` (tracked micronutrients, cited references), `food_label.py` (reads a nutrition table from OCR text; saves nothing), `ocr.py` (Tesseract only), `goal_store.py` (goals table: race/performance/distance/weight; the nearest standard-distance run race drives the weekly plan), `journal.py` (habit check-ins), `strength.py` (named classes), `weightlog.py` (manual weight entries, one per day, source `manual`), `profile.py` (height/birth date/sex, used only by `analytics/body.py`'s cited body estimates — never presented as measured), `push.py` (Web Push), `share.py` (phone server; paired phones may write only push, `/api/journal/*`, `/api/strength/*`, `/api/planner*`, `/api/weight/entries`, `/api/settings/weather` and `/api/settings/profile`), `credentials.py`/`secrets.py`.
- `analytics/`: `wellbeing.py` (what a check-in changes), `outcomes.py` (12 weeks vs the 12 before), `accuracy.py` (prediction scoring + self-correction), `banister.py` (personal τ fit, adopted only if it wins held-out CV), `routes.py` (repeated-route matching from summary GPS fields), `whatif.py` (counterfactual replay with ranges), `fatigue_fit.py` (personal recovery speed from HRV/RHR), `channels.py` (easy vs hard minutes → efficiency), `freshness.py` (does starting fresh improve your hard runs), `regress.py` (OLS with Newey–West), `goals.py` (feasibility per goal kind), `athlete.py` (load, readiness, efficiency, effects), `performance.py` (critical speed, FIT run analysis), `recovery.py` (HRV-guided, recovery cost, sleep need/tonight), `plan.py` (periodisation), `habits.py` (journal effects), `exercises.py` (class parsing, HR block segmentation), `strain.py` (all-day strain), `score.py`, `insights.py` (loading + `assemble()`), `notes.py` (wording).
- User-entered data (journal, strength labels, goals) is keyed so an offline rebuild never loses it (strength labels by Garmin activity id, not row id).
- `food-data/` — private submodule: the food library crawl (`tools/crawl_library.py`) and the catalogue built by `cadence_app/food_import.py`; `foodlog.py` loads it (dishes, entries with micronutrients, saved meals). Without the submodule the app still works with your own dishes.
- `tools/demo-media/` — records the demo tour (synthetic data, throwaway server), renders the algorithm explainers (`build-explainers.sh`) and encodes README WebPs and social GIF/MP4s; marketing tooling, kept out of `app/` (`build.sh`).
- `deploy/` — server setup, push, systemd units and encrypted Drive backup scripts (`docs/deploy-digitalocean.md`).
- `app/web/src/` — React 19 + Vite + Tailwind 4 + ECharts + MapLibre; `pages/`, `components/`, `lib/` (API client, formatting, metrics). Tests are Vitest (`*.test.ts`).

## Conventions

- Match surrounding code style; the repo has no linter config, so follow existing idioms.
- Garmin sync must stay idempotent, resumable and rate-limit aware (1 req/s, back off on 429). Settled days (>3 days old) are fetched once; rebuilds from the vault make zero API calls — keep it that way (see the `garmin-vault` skill).
- Rename leftovers: the project was previously "WeighIn"; use `cadence_*`, `X-Cadence-Request`, `CADENCE_*`.
