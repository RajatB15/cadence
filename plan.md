# Cadence Product Plan

Last updated: 2026-10-24.

## Direction

Build a single-user, local-first health and training web app, then package the validated experience as a standalone macOS app. LLM integration is the final stage.

Differentiate through transparent analytics, cross-source context, customizable workflows, and data ownership. Garmin already provides overlapping trends, readiness, training load, and summaries; verify current product capabilities before claiming a feature is unique.

The web-first roadmap supersedes the earlier iOS-first roadmap. No cloud account or hosted backend is required initially.

**Store everything, surface what matters:** every imported response stays in the vault; product pages show curated views and derived insights, and raw records remain inspectable in the Vault data explorer.

## Current State

- Built (2026-10-22): local FastAPI backend and SQLite schema under app/backend; React web app under app/web; deterministic demo connector; weight trend analytics; credential expiry status, banner, and settings timeline. Verified with backend/frontend tests and in-browser checks at desktop and mobile widths.
- Verified on 2026-10-22: official Garmin Personal API key exchange and authenticated reads, with a full-history core backfill (activities, daily summaries, sleep, HRV, Body Battery, weigh-ins) completed against a real account back to its history start, in well under 200 API calls. Deep archive (FIT files, activity details/workouts, intraday HR/HRV, SpO₂, fitness age) runs in the background.
- Garmin vault: every response is stored compressed in SQLite (`raw_responses`), FIT ZIPs under `data/archive/garmin/fit/` (0600). Dashboards are derived from the vault and can be rebuilt offline with zero API calls. Days older than 3 days are fetched once and never re-requested; each later sync makes about one request per dataset.
- Once Garmin has data, all dashboard queries select Garmin records exclusively; demo records are never blended with real observations.
- Unverified: scale protocol, Garmin rate limits (none hit so far), and personal-use storage terms beyond the FAQ ("personal applications using their own data"). Published Swagger lists 26 read-only endpoints and no weight-upload endpoint.
- Not built: export/backup, tags, deeper analytics, app packaging, OS notifications. Remaining datasets without purpose-built views (auto-detected moves, food logs) are viewable via the day "Everything recorded" panel and the Vault data explorer.
- Coach / analytics (2026-10-22): `/coach` page backed by `analytics/athlete.py` (pure algorithms) and `analytics/insights.py` (assembly, rules, plan). Readiness score (HRV/RHR z-scores vs 60-day baseline, sleep score, form), Banister fitness/fatigue/form and EWMA acute:chronic ratio, weekly monotony/strain/rest days, 80/20 intensity distribution from HR-zone time, aerobic efficiency (grade-adjusted pace per heartbeat, Theil–Sen trend), Pa:HR decoupling from FIT streams (cached per run in `activity_analyses`), sleep timing regularity, lagged personal effects (Welch t-tests, n ≥ 8 per group), a rule-based "what you're missing" list, and a 7-day prescription using Garmin lactate-threshold HR zones. Raw-dump panels were removed from product pages; the Vault data explorer remains for inspection.
- Coach everywhere (2026-10-22): `analytics/notes.py` builds on a shared per-request insights context (~0.1 s). Home leads with today's call (readiness ring + concrete session from the weekly plan, HR targets from Garmin zones), this week vs plan (load band, sessions, quality sessions, long run, easy-kept-easy, sleep, lights-out), an athlete score with five pillars and week-over-week deltas (fitness vs 1-year peak, 7-day readiness, sleep, consistency, intensity balance), streaks with personal bests, and the top issues to fix. Every session gets a verdict (Easy, Long & easy, Key session, Grey zone, Hard again, Long & hard, High intensity) and notes: intensity mix vs readiness and recent hard days, load percentile, efficiency vs similar-HR runs, HR drift, pacing split, next-morning HRV response, late-finish sleep cost, distance/pace milestones, unlabelled strength sets. Every day gets metric-tagged notes (sleep duration with a bedtime from the wake time, sleep quality with likely contributors, deep/REM lows, HRV and RHR vs baseline, stress, Body Battery, steps, SpO₂, respiration, load/ACWR, weekly intensity minutes), and weigh-ins get frequency, rate-vs-goal and goal-path notes.
- Lab + Goals (2026-10-24): `/lab` (Accuracy, Fitness model, Routes, What-ifs) and `/goals`. Prediction accuracy scores planned sessions and a walk-forward backtest (log-ratio t-interval; bias needs 10+ sessions; shrunk, capped per-sport correction stored beside the raw load). Personal Banister fit on weekly aerobic efficiency (grid search, F-test region with autocorrelation-shrunk n, adopted only if 5-fold blocked CV beats both 42/7 and the mean); monthly critical speed gives too few points to fit. Repeated routes matched from Garmin summary fields (no FIT decode). What-if replay reruns the same PMC with a session skipped/halved/kept easy. Goals table (migration 0010 moves the old training/weight goal settings): race, performance, distance, weight in run/ride/swim; run times use a CS Monte Carlo, ride/swim a labelled heuristic from best recent sessions. Verified with synthetic-data tests and in-browser at desktop and phone widths; not yet judged on real data.
- Check-in, maintain, outcomes (2026-10-24): a daily self-report (feel, soreness, pain with area, illness, life load; migration 0011, phone-writable) that overrides Home's call and today's session towards rest/easy, holds the week back (absorb) for recent pain or illness or several flat days, and trims the week 10% under heavy life load; it never adds training. Patterns (recurring pain, trained through pain/illness, feel vs watch disagreement, feel drop) become coach notes. A Maintain phase (no goal, mode auto/build/maintain; auto after 8 flat weeks of fitness) holds load at your chronic level with one quality session. "Recovery wins" on Home. `/api/outcomes` and the Coach card "Is it working?" compare the last 12 weeks with the 12 before (markers with a noise floor, training context, adherence, pain/illness days; no causal claims). Ride/swim and non-standard goals with a date set the plan's phases and a long-session target for that sport (a standard-distance run race still takes precedence). Food/fuelling is deliberately out of scope for now.
- Model upgrades (2026-10-24): what-ifs now (1) measure whether freshness improves your hard runs (best 5-min speed vs form, OLS with HAC errors, only priced when the interval excludes 0), (2) split load into easy (Z1-3) and hard (Z4-5) minutes against weekly efficiency (adopted only if it beats total minutes in blocked CV; Z3 counts as aerobic so grey→easy moves no minutes), (3) fit your own fatigue time constant from overnight HRV/resting HR (adopted at ≥10% CV gain), (4) show ranges over the plausible time constants (or textbook 35–50/5–10 days), (5) test diminishing returns (load^α, adopted at ≥5% CV gain). Personal constants apply only inside what-ifs; Home/Coach fitness/fatigue/form stay on 42/7. Synthetic-data tests; not yet judged on real data.
- Lab everywhere (2026-10-24): Predictions and Fitness model tabs open with a plain-language Q&A built from the numbers (`notes.accuracy_explain` / `model_explain`). Repeated-route context appears on each run/ride page (rank, vs usual, value per heartbeat, trend). What-ifs surface as a motivating card on Home (last 4 weeks), on flagged sessions (grey zone or a hard day after a hard day), and in weekly/monthly reviews (praise when nothing needed fixing); each links to the replay.
- Renamed WeighIn → Cadence (2026-10-22): package `cadence_app`, header `X-Cadence-Request`, env `CADENCE_*`, database `data/cadence.sqlite3`.
- iPhone access (2026-10-22): opt-in, read-only share server (`cadence_app/share.py`, port 8766, all interfaces) started from Settings. QR pairing key → HttpOnly cookie; GET/HEAD only; `/api/share` blocked from phones; serves the built `app/web/dist` with a read-only marker so the UI skips on-demand fetches; resumes on restart. Home-screen install via web manifest + apple-touch-icon. Plain HTTP on the LAN; use Tailscale for remote access. Rebuild `dist` after frontend changes.
- Cloud hosting (2026-10-24): `deploy/` + `docs/deploy-digitalocean.md` run Cadence on a ~1 GB DigitalOcean droplet (Ubuntu 24.04, systemd, ufw with only SSH open, Tailscale for the phone via the share port, nightly rclone-crypt backups of the database and Garmin archive to Google Drive, never the Garmin key). Install, run, demo sync, weight logging and an encrypted backup/restore round trip were tested in a clean Ubuntu container; systemd, ufw and the live droplet are untested until first deploy.
- Direction (2026-10-22): one always-on Cadence service + the web app on every device, joined by Tailscale. A native iOS app is only worth it for HealthKit, or background sync; the standalone macOS app (Stage 8) is deferred in favour of the login service. Raspberry Pi / Mac mini hosting to be evaluated so the phone doesn't depend on the laptop being awake.
- Login service + notifications (2026-10-22): `scripts/cadence-service.sh` installs a LaunchAgent (RunAtLoad, KeepAlive; logs in ~/Library/Logs/Cadence). The backend now serves the built site on :8765. `cadence_app/push.py`: VAPID + RFC 8291 Web Push (py-vapid, http-ece, httpx), subscriptions restricted to known push services, `notification_log` makes each notification fire once; scheduler syncs Garmin every 3 h (45 min on mornings) and sends the morning readiness brief, session verdicts, 21:00 bedtime nudge and key reminders, each toggleable. Paired phones may only write to `/api/push/*`. Share card detects `tailscale serve` and pairs to the https://…ts.net address. iOS push requires the Home Screen app over HTTPS (Tailscale).
- Readiness v2 + Cadence Score (2026-10-23): Garmin's Training Readiness isn't exposed by the personal API, so readiness was rebuilt on its factors: sleep score 25%, 3-night sleep 10%, HRV vs Garmin's balanced range 20%, resting HR in bpm vs 60-day normal 10%, load (ACWR + form) 20%, Body Battery 15%; a normal day scores ~80, matching the comparable Garmin figure on real test data. After a session, Home compares it with what the day called for (matched / open / harder / extra) and only suggests an optional easy second session before 19:00 with readiness ≥ 70. Home shows today's (or the latest) sessions with verdict and headline note. `analytics/score.py` computes a daily Cadence Score from 15 factors in Train 30% / Recover 30% / Sleep 25% / Move 15%, recomputable for any past day, with points lost per factor; `/score` shows rings, a radar of every factor, the 100-point bar, ranked gaps with fixes, 30/90/365-day history and per-area factor cards.
- Live readiness + minimal Home (2026-10-23): new `body_battery_now` metric (Garmin's `bodyBattery.latestValue`). Today's readiness starts from the morning score and moves through the day: Body Battery drain (half-weighted, so normal evening decline isn't punished) and a per-session strain cost (up to 35 load points, scaled by load vs fitness, recovering with a 7 h half-life), with a "since this morning" breakdown. The day's plan still uses the morning score. Scheduler syncs hourly 11:00–23:00 (45 min mornings, 3 h overnight); Home refetches every 5 min. Home is now two dials (live Readiness, Cadence score) with detail sheets, a compact Today card with expandable "why", today's sessions, a week strip of mini rings (sheet for the full list), a "biggest gain" line, a swipeable vitals strip and streak chips. Motion: rings rotate in and count up, sparklines draw themselves, bars grow and ECharts animate as each scrolls into view.
- Analytics review (2026-10-23): fixes — walks no longer dilute the 80/20 split or count as training sessions; aerobic efficiency is speed per beat above resting HR (ACSM/Swain), so pace-at-HR is right away from the median HR, and interval runs are excluded; readiness weights rebalanced (HRV 25%, RHR 15%, Body Battery 5% since it is derived from HRV/sleep) and checked against same-day run efficiency (`readiness_validation`, suggested weights shown, never auto-applied); one personal sleep need everywhere (broken-stick plateau of overnight HRV vs sleep, 8 h default); lagged effects use regression with weekend/load covariates, autocorrelation-inflated SEs and Benjamini–Hochberg FDR; sprint sessions count as hard by anaerobic TE ≥ 3; ACWR > 1.5 only alerts when corroborated (run-km spike or warning signals) and has half weight in the score; recovery/taper weeks are not penalised. New modules: `analytics/performance.py` (Minetti grade-adjusted speed, best efforts, critical speed + D′ with validity checks, race predictions, CS pace bands, zone staleness check, cadence-at-speed and late-run fade trends; FIT analysis v2 for every run ≥ 10 min), `analytics/recovery.py` (HRV-guided ln RMSSD 7-day vs ±0.5 SD band with CV coping, personal recovery cost by session type → quality-session spacing and live-readiness half-life, sleep need, Sleep Regularity Index, two-signal illness/overreach warning, RED-S pattern) and `analytics/plan.py` (goal-aware periodisation: base/build/specific/taper/race counted back from a race goal set on the Coach page, 3:1 blocks without one, CTL ramp ~6%/week capped at 1.25 × chronic, long run +10 min/week capped at 110% of the 30-day longest run, rotating progressive threshold/VO₂/race-pace sessions with HR and CS pace targets, strength 2×/week). Verified against a real vault of archived runs: critical-speed fits converge from the analysed FIT history, hard-session recovery timing is learned from isolated sessions once enough exist; readiness validation needs 20+ comparable runs before it reports.
- Day explorer (2026-10-22): every metric page is a day explorer — pick a day (click the trend, arrows, or ←/→) to see its value against the 7-day/30-day averages, 60-day baseline, prior week, all-time range, rank and percentile, plus metric-specific panels: HRV (baseline band, status, overnight 5-minute readings), all-day heart rate, sleep (stages, timing, score components, SpO₂/respiration), Body Battery timeline, stress breakdown, movement goals and energy, SpO₂ hourly, breathing, sessions, fitness age, hydration. Intraday detail not yet archived is fetched once on first view of a day.
- Activity detail page (2026-10-22): decodes each archived FIT file with Garmin's official FIT SDK and shows headline stats, HR zones, every recorded channel as linked charts, the GPS route, laps/splits and strength sets. Missing per-activity assets are fetched once on first open; raw fields stay in the Vault data explorer.
- Route maps (2026-10-24): the activity route is a MapLibre GL v6 map (lazy-loaded) on free, keyless providers — OpenFreeMap Dark/Streets (OSM data), EOX Sentinel-2 cloudless 2025 satellite (CC BY-NC-SA 4.0: personal, non-commercial use with attribution) and AWS/Mapzen terrarium elevation for 3D terrain + hillshade. The route is a glowing line gradient by pace/speed, heart rate or elevation (FIT decode now emits a `track` with per-GPS-point t/hr/speed/alt/dist), with start/finish pins and collision-aware km badges. A 3D chase-cam flyover follows the trail, with an elevation-profile scrubber and live time/distance/pace/HR/elevation readout; fullscreen; 3D is the default when relief ≥ 60 m. Tile requests reveal the viewed area to those providers (accepted by the user); no activity data is sent. Without WebGL or if the style can't load, the locally drawn route shape is shown.

## Technology

| Layer | Choice |
| --- | --- |
| UI | React, TypeScript, Vite |
| Styling and controls | Tailwind CSS, accessible Radix primitives, Lucide icons |
| Charts | Apache ECharts |
| Local backend | Python, FastAPI, Pydantic |
| Persistence | SQLite, SQLAlchemy, Alembic migrations |
| Source archive | Original responses and activity files in a local application-data directory |
| Analytics | NumPy, pandas, SciPy; statsmodels when justified |
| Jobs | One local worker with persisted job state; no Redis initially |
| Tests | pytest, Vitest, Playwright |
| macOS shell | Tauri provisionally; validate Python sidecar and signing early |
| LLM | Provider-independent adapter added last |

Avoid microservices, cloud databases, Kubernetes, and vector databases until a concrete need exists.

## Data Architecture

Garmin API/exports and optional external sources feed connectors. Preserve raw source data, normalize into SQLite, then compute versioned analytics exposed by the local API to the web UI.

- Separate source records, normalized records, and derived results.
- Retain source IDs, timestamps, units, provenance, calculation version, and freshness.
- Normalize instants while preserving source timezone and local-day semantics.
- Make imports idempotent, resumable, and rate-limit aware; persist checkpoints and retry state.
- Core browsing must work offline after import. Provide portable export, backup, and deletion.

## Roadmap

Estimate delivery dates after API verification and a representative data sample.

### Stage 0: Access and Packaging Spikes

- [x] Obtain official documentation for this credential type (Personal API page, FAQ, Swagger, garmin/connect-personal-api-python).
- [x] Verify authentication, endpoints, historical depth, pagination, and raw activity/FIT access. Access tokens last 24 h (renewed at 23 h); no refresh tokens. Rate limits are undocumented: client throttles to 1 req/s and backs off on 429 / Retry-After.
- [x] Establish whether weight/body-composition writes are supported: no write endpoint is published.
- [x] Verified documented authentication and daily-summary read on 2026-10-22 without printing the key, access token, or personal response body.
- [x] Define capability flags: datasets returning 401/403, or probes returning no data, are marked unavailable; other datasets continue.
- [ ] Spike Tauri/Python sidecar startup, lifecycle and signing requirements.

Gate: document observed capabilities without inventing endpoints. Unsupported writes disable Garmin upload, not local scale storage or the rest of the app.

Official sources: [Personal API authentication](https://developer.garmin.com/gc-developer-program/personal/personal-api/), [Personal API Swagger](https://developer.garmin.com/gc-developer-program/personal/swagger-docs/), and [program overview](https://developer.garmin.com/gc-developer-program/overview/). Token exchange: POST `/personalapitoken-service/personal-api/personal-api-key/token` with `Authorization: ApiKey ...`; observed response is a plain-text access token. Data host: `https://personal.connectapi.garmin.com`, Bearer authentication.

Observed limits (2026-10-22): Swagger says daily summaries accept 1-year windows, but Garmin returns HTTP 500 above ~120 days. The engine treats 400/500 on a range window as "too large", halves and persists the window size, and only treats a failing single day as a transient error. Defaults: daily summaries/weight/goals 120 d, activities 180 d × 50 per page, sleep/HRV/Body Battery 31 d.

### Stage 1: Data Foundation (Idea 10)

- [x] Create local backend, schema/migrations, and connector boundary.
- [x] Add raw source archive (Garmin vault) and a background worker with persisted checkpoints, stop, and resume.
- [x] Implement historical backfill and incremental sync for verified datasets; offline rebuild from the vault.
- [x] Expose sync progress, failures, freshness, and available capabilities (Vault page).
- [ ] Implement export and backup. (Demo-data deletion is implemented.)
- [x] Implement credential expiry status and renewal reminders specified below (in-app; see criteria for remaining items).

Gate: repeated imports do not duplicate records (verified); interrupted sync resumes (verified live); rebuild makes zero API calls (verified by test); secrets never reach the browser (verified by test).

### Stage 2: First Usable Web Release (Idea 2)

- [x] Build overview, activity explorer, and sleep, HRV, resting-heart-rate, stress, and weight timelines (demo data).
- [ ] Add manual context tags. (Schema exists; no API or UI yet.)
- [x] Add smoothed weight trends, uncertainty, and cautious goal projections.
- [x] Display credential renewal status and test desktop/mobile layouts.
- [ ] Verify offline browsing and add a Playwright end-to-end suite.

Gate: connect or import, backfill, browse, tag, and export work end to end. Missing data is explicitly distinguished from zero.

### Stage 3: Weight Logging and Body Stats (revised 2026-10-23)

Garmin has no weight-upload API (Personal API is "Pull only": 26 published endpoints, all reads), so weight
is logged by hand in Cadence or comes from Garmin weigh-ins. A direct scale integration was tried and
dropped because its readings did not match the scale's own display. Nothing in the app talks to a scale.

- [x] Manual weight log (`cadence_app/weightlog.py`, source `manual`): one entry per day, re-logging a day
  corrects it, `GET/POST /api/weight/entries` and `DELETE /api/weight/entries/{day}`, blended with the active
  source in the trend. Paired phones may write `/api/weight/entries`. Log dialog on the Weight page and a
  "Log weight" chip on Home.
- [x] Body profile (`profile.py`): height, birth date, sex - used only by the estimates below.
- [x] `analytics/body.py`, all labelled as estimates with sources in the UI: BMI (exact) with WHO categories,
  healthy weight range (BMI 18.5-24.9), Deurenberg (1991) body fat %, fat/lean mass, Mifflin-St Jeor (1990)
  BMR, daily energy ranges (BMR x FAO/WHO/UNU 2004 activity bands 1.4/1.7/2.0), Mosteller (1987) body surface
  area. Muscle %, bone mass, visceral fat, water % and metabolic age are not computed.
- [x] Weight page "Body stats": BMI gauge, healthy-range bar with goal marker, fat vs lean bar, energy bars;
  empty, loading, no-profile and phone-width states.

Gate: nothing presented as measured that isn't; every formula cited with its source and limitations.

### Food log (added 2026-10-24)

Local food log tuned for home-cooked Indian food; no Garmin involvement.

- [x] (superseded by the HealthifyMe entry below) Personal dish library (`foodlog.py`, tables `food_dishes`/`food_entries`, migration 0012): about 80 starter dishes with rounded typical per-serving values (not measured; to be cross-checked against IFCT 2017), editable, plus your own dishes. Entries copy nutrition at log time.
- [x] Quick entry for eating out, copy-yesterday, recent dishes first, per-entry spread (home +/-20%, out +/-30%, packaged +/-10%) shown as daily kcal ranges; unlogged days are "not logged", averages need 4 logged days; protein g/kg against the ISSN 2017 reference range.
- [x] `/api/food*` routes, phone-writable; backend tests in `tests/test_foodlog.py`.
- [x] Food page and "Log food" chip on Overview (code written, frontend typechecks and unit tests pass for the new files).
- [ ] Verify the Food page in a browser at desktop and phone widths, then rebuild and restart the service.
- [x] Food source changed to HealthifyMe Nutrifacts (2026-10-25, replacing the starter, INDB and IFCT dishes). A personal-use, polite, resumable crawl (`food-data/tools/crawl_healthifyme.py`) stores per-100 g values, portions with grams, the full nutrient table, the `verified` flag and the named recipe source for each page. The data lives in the private `cadence-food-data` repo, mounted as the `food-data/` submodule; nothing from it is committed here (this repo is public). `cadence_app/food_import.py` builds `catalogue.json`: drops rows that can't be right, merges alias pages (identical nutrient tables) into one dish with search aliases, keeps portions and the source note. `foodlog.py` loads it, retires the older built-in dishes (entries keep their own copy; edited ones become yours) and keeps your own dishes.
- [x] Grams are the standard unit: per-100 g nutrition and a weight for every portion; log by portion x count or by grams.
- Known limits: HealthifyMe's numbers are calculated from web recipes and marked unverified (spot check vs IFCT 2017: paneer -13%, cooked rice -24%); the app labels them as estimates with their source. IFCT 2017 / INDB are no longer used; re-adding IFCT as a cross-check is possible.
- [ ] Finish the crawl (about 9,000 pages, several hours), run `food_import`, spot-check the catalogue against IFCT, then restart the service.
- [ ] Later: intake vs estimated energy use (`analytics/body.py` ranges) and vs training load; edit/deactivate dishes in the UI; LLM text/photo estimates (last stage).

### Stage 4: Personal Analytics (Ideas 3-6)

- [x] Idea 3: lagged associations across metrics (load, sleep, bedtime, workout timing, stress, steps) with sample sizes and significance; tags not yet included.
- [x] Idea 4 (first pass): transparent readiness score from HRV/RHR baselines, sleep and form, validated against same-day run efficiency (Spearman). Forecasting still pending.
- [x] Idea 5 (first pass): HRV and resting-HR deviation findings vs personal baseline, not diagnoses.
- [ ] Idea 6: weight versus aerobic efficiency — blocked by sparse weigh-ins (flagged as a data gap).

Gate: reproducible calculations, uncertainty, minimum-data rules, and no causal or medical claims unsupported by evidence.

### Stage 5: Training Lab (Ideas 7-9)

- [x] Idea 7: transparent fitness/fatigue/form (42/7-day EWMA) with acute:chronic ratio and visible assumptions.
- [x] Idea 8: repeated-route matching and effort comparison (Lab → Routes); weather shown as context, not adjusted.
- [x] Idea 9: heart-rate drift (Pa:HR) on grade-adjusted pace for runs ≥ 45 min; late-run fade on runs ≥ 75 min; unsteady-pace runs excluded.
- [x] Critical speed / D′, race predictions, pace bands and HR-zone staleness from best efforts.
- [x] Periodised plan with optional race goal, 3:1 blocks, run-specific spike caps and HRV-guided gating.
- [x] Personal Banister fit (individual time constants): implemented on weekly aerobic efficiency, adopted only when it wins held-out CV (see Lab).

Gate: test on controlled fixtures and representative activities; unsuitable activities get explicit exclusions.

### Stage 5b: Behaviour, Strength Content, Adaptive Sleep, All-Day Strain (2026-10-23)

Closes the software gaps against WHOOP that matter for training (journal insights, adaptive sleep need, all-day strain), plus strength-session content. Hardware/medical features (skin temperature, ECG, clinician visits) are out of scope.

Phase 1 — Journal and behaviour insights
- [x] Migration: behaviour catalogue (key, label, question, kind yes/no · count, active, sort) and daily answers (day, behaviour, value, answered_at); fold in the unused `tags` table.
- [x] Default behaviours asked each morning about yesterday: alcohol (drinks), caffeine after 14:00, late big meal, screens in bed, sauna/heat, stressful day, travel/time zone, felt ill, mobility, nap; custom behaviours allowed.
- [x] API: catalogue CRUD, answers for a day, check-in status. Paired phones may write only `/api/journal/*` (and later `/api/strength/*`); everything else stays read-only.
- [x] Morning check-in sheet on Home (offered until answered), journal history page section, morning push mentions it.
- [x] Insights: behaviours with ≥ 8 yes and ≥ 8 no days feed the effects engine (overnight HRV, resting HR, sleep score, readiness, next-day run efficiency), adjusted for load and weekends, FDR across all tests; "What your habits cost you" section and coach notes.

Phase 2 — Strength content from class screenshots
- [x] Paste text (iPhone Live Text) into "Name this class" on a strength/HIIT session; parse blocks and exercises; save as reusable template.
- [x] Exercise dictionary → movement pattern (squat, hinge, lunge, push, pull, carry, core, plyometric) and primary muscles; unknown names are kept and flagged. Labels are keyed by Garmin activity id so offline rebuilds keep them.
- [x] HR segmentation: warm-up / ordered blocks / cool-down by changepoint fitting on the HR trace (watch records one set per session, ~0.5 Hz HR: block-level only, never per-exercise). Per-block time, zones and load.
- [x] Coach: weekly pattern totals, heavy-legs-before-key-session and missing-pattern notes; plan strength target becomes 1 heavy lower + 1 full body.

Phase 3 — Nightly sleep need and bedtime
- [x] Tonight's need = personal plateau + strain-scaled extra + half of 7-day debt (≤ 60 min) − naps (naps aren't in the Garmin data yet, so not subtracted); capped at 1 h earlier than your recent lights-out so it's achievable.
- [x] Bedtime = weekday-specific usual wake − need − personal sleep latency; on Home, plan and a moving bedtime push (45 min before).
- [x] Validate: does hitting the target precede better next-day HRV/readiness?

Phase 4 — All-day strain
- [x] HRR-weighted TRIMP over all-day HR (near-complete history archived), from 35% of heart-rate reserve, calibrated to Garmin training load on workout windows (checked against real data: everyday movement can be a substantial share — roughly a third — of daily strain). Settled days cached as minute-per-bpm histograms; today and yesterday refetched each sync (+2 requests).
- [x] Live strain gauge vs a target band from readiness, the week's plan and recovery cost; non-workout strain shown in the load chart.

Gate: each phase ships with synthetic-data tests, a counts-only check on the real vault, phone and desktop screenshots on demo data, and a commit.

### Stage 5c: Planning (2026-10-23)

Plan any of the next 7 days by sport. Strength: upload the class screenshot up front. Run, ride, swim: Cadence recommends sessions for that day and predicts what each will do before you commit.

- [x] Personal load model: your load per minute on similar sessions × planned minutes, adjusted for intensity by a monotone zone model (Garmin's EPOC-based load fits zone minutes loosely — moderate R² on real data — so the zone model only nudges ×0.6–1.6); fallbacks: same sport's easy sessions for long/recovery, same effort in your other sports, zone model, general. Strength from past classes.
- [x] Session library: run (recovery, easy, long, the plan's progressive key sessions: threshold, VO₂max, hills/strides, race-specific), ride (recovery spin, endurance, tempo, threshold, VO₂; HR targets ~5 bpm below running zones, no power data), swim (technique, aerobic, threshold set, sprints; effort by feel because wrist HR in water is unreliable), each as a zone-minute profile.
- [x] Ranking for the chosen day: readiness (today) or a normal day (future), HRV-guided status, early-warning signals, personal hard-session spacing including other planned sessions, week targets still open (quality, long run, load band), no heavy legs before a planned key run. One recommended, the rest with reasons or cautions.
- [x] Predicted outcomes per option: training load (with similar past sessions), day strain vs today's band, fitness/fatigue/form and acute:chronic the next morning, the training-load part of tomorrow's readiness, days for HRV to recover (personal), what it builds, expected Garmin aerobic TE from similar sessions, week-target progress, and a 4-week fitness projection if the plan is followed.
- [x] Storage: planned sessions (migration 0008); matched to the day's actual session of the same sport; a planned strength class labels the matched session automatically; plan-vs-actual on the session page (load and intensity vs prediction).
- [x] UI: Plan page (7-day strip → sport → options with predictions → plan it), today's planned session leads Home, phone tab bar swaps Vault for Plan (Vault stays in Settings); paired phones may write `/api/planner*`.

### Stage 5d: Reviews and Weather (2026-10-23)

Weekly/monthly reviews (part of Idea 13) and heat/weather context (part of Idea 11).

Reviews
- [x] Weekly review (Mon–Sun) and monthly review, each vs the previous period: a one-line verdict; training (sessions by sport, hours, km, load vs the plan's band, quality sessions, long run, intensity split, all-day strain); plan adherence (planned vs done, predicted vs actual load); fitness (fitness/form/acute:chronic at the end; monthly: critical speed, efficiency, VO₂max, weight trend); recovery (readiness, HRV vs normal range, resting HR, warning days); sleep (hours vs need, nights at need, regularity, bedtime); habits logged; strength patterns; highlights (biggest, longest, fastest, records); hot sessions; one focus for next week.
- [x] Reviews page (week/month toggle, step through history), Home card early in a new week/month, Coach link.
- [x] Push: weekly review Sunday 19:00, monthly on the 1st at 09:00 (toggleable).

Weather — live 2026-10-24: outdoor session history backfilled with conditions across rounded locations; personal heat cost needs 20+ qualifying runs, general Hadley table until then. (Open-Meteo, free, no account; only coordinates rounded to 0.1° (~10 km) and dates are sent; switch in Settings, on by default per the user's go-ahead)
- [x] Hourly temperature, humidity, dew point, apparent temperature and wind cached locally per rounded location: history from the archive API for every outdoor session (Garmin start coordinates), recent and next 7 days from the forecast API.
- [x] Personal heat cost: robust regression of run efficiency vs dew point above 10 °C on your own runs; if it's clear, efficiency and the efficiency trend are heat-adjusted, and hot runs are labelled on drift/durability.
- [x] Session notes ("28 °C, dew point 21 °C: most of the slower efficiency is heat"), and forecasts on planned runs/rides (conditions at your usual start time, expected slowdown, "go early" when it pays).

### Stage 6: Context and Actions (Ideas 11-12)

- [ ] Idea 11: weather, calendar summaries, and optional caffeine/meal context with explicit permissions.
- [ ] Idea 12: previewable digest/automation rules, opt-in notifications, and delivery history.

Gate: external integrations can be disconnected, provenance remains visible, and failed delivery is inspectable.

### Stage 7: Retrospectives (Idea 13)

- [ ] Build monthly/yearly reports and shareable graphics from verified statistics, including consistency and recovery patterns.
- [ ] Provide private previews and deliberate export rather than automatic publication.

### Stage 8: Standalone macOS Release

- [ ] Package validated web workflows with Tauri if the early spike succeeds.
- [ ] Move credentials to macOS Keychain with a deliberate migration from the local development file.
- [ ] Implement service lifecycle, app-data paths, installer/signing, and an update strategy.
- [ ] Validate sync resume, backups, and expiry reminders in the packaged app.

### Stage 9: LLM Integration (Idea 14, Last)

- [ ] Add read-only analytics tools and a provider adapter after the data/analytics workflows are verified.
- [ ] Answer questions with dated evidence, traceable calculations, and explicit uncertainty.
- [ ] Preview and obtain opt-in for health data sent to an external provider.
- [ ] Evaluate factual grounding and refusal to invent missing observations; no autonomous uploads or health decisions.

## Credential Storage and Renewal Reminder

Development credentials are stored only in the git-ignored `.secrets/garmin.env`, with owner-only directory/file permissions. This is plaintext storage, not encryption. Do not duplicate the key here or in any tracked file. Load it on the backend; do not expose it through Vite environment variables.

- `GARMIN_API_KEY`: local credential, never displayed or logged.
- `GARMIN_API_KEY_EXPIRES_ON=2027-10-22`: date supplied by the user as one year from 2026-10-22; not provider-verified.
- `GARMIN_API_KEY_REMINDER_DAYS=30,7,1`: initial reminder thresholds.

Reminder acceptance criteria:

- [x] Backend exposes only availability, configured expiry date, days remaining, and renewal status, never the credential itself.
- [x] Persistent settings status shows expiry; show a renewal banner within 30 days and escalate at 7 days, 1 day, and on expiry.
- [x] Initial reminder dates are 2027-09-22, 2027-10-15, and 2027-10-21; mark expired on 2027-10-22 using local calendar dates.
- [x] Recalculate on startup/resume and daily while running; surface missed thresholds on next launch.
- [x] Dismissal does not hide later escalation; deduplicate notifications by expiry date and threshold.
- [ ] OS notifications are opt-in and require permission. Do not promise delivery while the web app is closed; background delivery requires a separately validated desktop mechanism.
- [ ] Replacement updates credential and expiry together without exposing either key; reset reminder state for the new expiry. (Manual file edit works and reminder keys reset by expiry date; no in-app replacement flow yet.)
- [ ] Handle missing/malformed expiry and authentication rejection separately; a configured date does not prove the key is valid.
- [ ] Test threshold boundaries, leap years, timezone/day changes, resume after missed reminders, rotation, and notification deduplication with a controllable clock.

## Security and Quality Gates

- Bind the local service to loopback; protect browser requests with strict allowed origins and request authentication/CSRF controls as appropriate.
- Never commit credentials, raw personal records, local databases, or logs containing health data.
- Use synthetic fixtures or explicitly reviewed, redacted samples in tests.
- Never claim local data is encrypted unless encryption is actually implemented; plan backup and deletion accordingly.
- Run focused tests for every changed behavior.
- Maintain empty, missing-data, loading, failure, and unsupported-capability states throughout the UI.