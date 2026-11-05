# Review fixes

**Priority override (user): anything that can produce wrong numbers or wrong advice comes first — all of workstream D (D1–D8), then data-correctness items C2, C3, C5. Mobile/UX/security work proceeds in parallel but does not displace these.**

From the five-specialist review (mobile UI/UX, frontend code, backend/security, analytics, data/sync). Ordered by priority; mobile deployment first. Tick items when fixed and verified.

## P0 — safety, data loss, mobile blockers

### Workstream A: web app (app/web)
- [x] A1 `lib/api.ts`: timeout + abort signal, guard `res.json()`, distinct offline `ApiError`, no JSON content-type for FormData, retry skips 4xx
- [x] A2 Service worker: register at startup, app-shell precache (network-first navigations, cache-first hashed assets), stale-while-revalidate for GET `/api/*` with offline banner; `notificationclick` falls back to `openWindow`
- [x] A3 `useAppLifecycle`: no reload while a sheet/form is dirty; "update available" prompt instead; timeout on version fetch
- [x] A4 Contrast: raise `--color-dim`; use readable colour for text under 14px

### Workstream B: share server and API security (app/backend share.py, main.py, ocr.py, push.py, deploy/)
- [x] B1 Strict `(method, regex)` phone write allowlist, anchored; exclude Garmin push/delete and reading feed refresh unless intended; test enumerating all non-GET routes
- [x] B2 Per-device revocable sessions; single-use expiring pairing key; `Secure` cookie over HTTPS; failed-pair throttle; hash stored token
- [x] B3 OCR: Content-Length check + streaming cap, pixel limit, catch `DecompressionBombError`, one OCR at a time
- [x] B4 Deploy: systemd `MemoryMax` + sandboxing, backup.sh JSON safety and crypt-remote check, share bind host configurable

### Workstream C: data, sync, DB (app/backend db.py, garmin/, insights.py, main.py clock)
- [x] C1 `db.py`: `busy_timeout`, `synchronous=NORMAL`, connect timeout
- [x] C2 Atomic/upsert `rebuild()`: never delete activities (keep analyses); test for failure mid-replay
- [x] C3 Do not store bad bodies (non-JSON / non-ZIP) as `final`; test
- [x] C4 Alembic connection enables `foreign_keys`; audit migrations that batch-alter `activities`
- [x] C5 User timezone setting for "today"; remove naive/aware mixing

### Workstream D: analytics (app/backend analytics/)
- [x] D1 `plan.py`: cap weekly target against recent actual load; band top ≤ 1.25 × chronic; `ramp_pct` binds
- [x] D2 `plan.py`: long run based on recent longest run, not a 60 min floor; session floor respects base
- [x] D3 `recovery.underfuelling`: stronger data rules, missing efficiency is unknown, drop "RED-S" wording (also notes.py)
- [x] D4 `evidence.py` / `status.py`: HRV+RHR count as one marker, stricter rule, softened non-causal wording

## P1 — correctness and performance

- [x] A5 Lazy-load non-Home pages; dedupe MapLibre worker; invalidate only active queries after sync
- [x] A6 Touch: 44px targets, input font-size ≥ 16px, heatmap tap-to-select, safe-area left/right, `@media (hover:hover)`, table overflow wrappers, chart tooltip `confine`, replace native `confirm`
- [x] C6 Cache: single-flight context build, cheaper `data_version`, stale-while-revalidate on writes
- [x] C7 Slim `activity_summaries` index; composite index on `raw_responses`
- [x] D5 `performance.py`: critical-speed residual gate, ≥ 4 points, CI, cap race-time model range; goals feasibility accounts for overlapping fits
- [x] D6 ACWR cold-start (None / warming up for first 28 days); `compare()` missing covariates; `score.intensity_minutes` min days; `sleep_pattern` calendar window; weekly partial-day
- [x] D7 Banister: MIN_OBS 30, fold gap, nested alpha; `sleep_need` Newey–West + edge-knot reject; `efficiency_trend` span ≥ 60 days

## P2 — polish

- [x] A7 Chart option memoisation, `echarts.connect` cleanup, manifest (maskable, id, lang), autofocus on coarse pointers only, grain overlay on coarse pointers
- [x] D8 `outcomes.py` inclusive window and min n; `trends.py` prediction interval; HAC df; freshness MIN_HARD; docstring fixes; readiness_validation BH correction
- [x] Tests for every fix above (plan caps, CS rejection, ACWR warm-up, rebuild atomicity, bad-body retry, write-allowlist enumeration, api.ts)

## Status (2026-11-05)

All items implemented and tested (backend 445 passed, web 122 passed). Known deviations / open items:
- A7 maskable icon skipped (cannot verify safe zone; no new binary assets).
- Heatmap tap selects and shows detail; no per-day page to open.
- C4: Alembic keeps foreign_keys off (batch rebuilds would cascade-delete analyses); runs foreign_key_check instead.
- C6: no stale-while-revalidate (writes invalidate immediately so you read your own writes).
- D8: freshness non-collider definition not changed (docstring caveat added).
- Open: `goals.cs_needed` does not use the Riegel blend; `notes.py` treats today's partial week as complete; `whatif.py` and `accuracy.py` not audited; web and server phone-write allowlists are kept identical by hand.
