# Home rethink: design spec

Status: proposal (read-only survey of the code, nothing built). Rules followed: CLAUDE.md and plan.md (cautious analytics, sample sizes shown, missing is not zero, estimates labelled, phone first).

## A. Survey: what exists

**Home today** (`app/web/src/pages/Overview.tsx`, 881 lines; `GET /api/overview` in `main.py:717`). Order: greeting, PhaseBanner, two Dials (Readiness, Cadence score), Today's read, StatusCard, check-in, wellbeing, review prompt, chip row (log weight/food...), PlannedToday, TodayCall, Strain, Weather, Tonight, Recent sessions, Improve, What-if, Week strip, Biggest gain, **VitalsStrip (near the bottom)**, streaks, recovery wins. About 20 blocks; the vitals the user wants are the 15th or so.

**Payload**: `metrics[]` for `OVERVIEW_METRICS` (hrv, resting_hr, sleep_hours, sleep_score, body_battery, stress, steps, intensity_minutes, vo2max) with latest, 7-day mean, 60-day baseline (needs 14+ points), delta_pct, 30-day spark; `coach` (`notes.brief`), `score`, `weight`, `journal`, `planned_today`.

**Per-day vault signals** (`daily_metrics`, `garmin/normalize.py`):
- Available: steps, floors, resting_hr, stress (avg), body_battery (day max), body_battery_low, body_battery_now (live), **active_calories**, **total_calories** (`burnedTotal`), calories_consumed (Garmin's own, likely unused), intensity_minutes, respiration, spo2, hydration_ml, sleep_hours/score/stress, HRV (+ weekly, balanced low/high), weight, activity `calories`/`training_load`.
- Food log (`foodlog.py`): per-entry kcal, protein/carbs/fat, micronutrients; `day_summary()` totals; entries have a meal slot but only a day (check: no reliable time-of-day, so intake cannot be curve-modelled, only summed).
- Goals: weight goal (`goal_store`, `start_value`, target date). Profile: height, birth date, sex (`profile.py`).
- `sleep_tonight` (`recovery.py`) and `sleep_pattern` (avg bedtime, SD) exist; `tonight` is in the brief.

**Missing**
1. **Intra-day burn history.** `total_calories` is one value per day, overwritten at each fetch; the raw response for today has a unique `request_key`, so earlier snapshots are lost. The "fraction of final total burned by 14:00" curve cannot be derived from the vault today. Needs a snapshot table.
2. No resting (BMR) series: derive `resting = total - active` on settled days.
3. No time-of-day awareness in `/api/overview` apart from one `hour < 19` check, which only gates the optional second session.
4. No calorie target setting, no maintenance estimate.
5. Food entries lack a logged-at time (confirm in `FoodEntry`; if absent, "nothing logged yet" is judged per day).

**The 10 pm bug**: `notes.today_session` (`notes.py:~830-885`) sets `status="open"` and titles "Key session still open" / "Long run still open" / "Aerobic work still open" whenever the planned session is not matched, with no hour check. Only the "Optional evening easy" extra uses `hour < 19`. The fix belongs in the phase engine (C), not in more `if hour` branches.

## B. Calories card

**Definitions** (all labelled estimates). Garmin `total_calories` = resting + active burn so far today, and it rises all day; the card must say "so far". Intake = sum of today's food-log kcal. Never present the balance as measured.

**Numbers shown**
- Burned so far: `total_calories` (big numeral), split resting / active as a two-tone arc.
- Eaten so far: food-log kcal, or "Nothing logged yet" with a **Log food** button. Absent is not zero: no balance and no "left" is computed from an empty log; the ring shows burn only.
- Projected end-of-day burn: `P` with range `[lo, hi]`.
- Left to eat: `target - eaten`, shown only when something is logged, or as "Target 2,350 kcal" otherwise.
- After a workout: active kcal from activities done today appear as "+420 from Run". Framed as fuelling: "A run like that usually calls for a refuel: a meal with carbs and protein within a couple of hours helps recovery." Eat-back is optional: a toggle in settings "Add today's workout burn to my target" (default: add 50% of workout active kcal, not 100%, because of estimate error; user-editable 0/50/100).

**Projection (`analytics/energy.py`, pure)**
`project_burn(now_frac, total_so_far, active_so_far, history)`:
1. Resting accrues roughly linearly: `resting_final ~ median(total-active)` over the last 14+ settled days (min 7), scaled by nothing else. Needs no snapshots.
2. Active remaining: if snapshot history has >= 10 days with a snapshot within 45 min of this local time, use `ratio_i = total_at_t / total_final` per day; `P = total_so_far / median(ratio)`, range from the 20th and 80th percentile of the ratios (min 10 samples). Show "based on 14 past days at this time".
3. Fallback (7 to 9 settled days, no snapshots): `P = total_so_far + (resting_final - resting_so_far_expected) + typical remaining active` where typical active = median of past days' active kcal, range from its quartiles. Label "rough: only 8 days of history".
4. Under 7 settled days or no Garmin kcal: return `{status: "insufficient", n}`; UI says "Not enough history yet for a projection (need a week of days)".
After 21:00 the range collapses to `+/- 5%` of so-far (little burn remains); the projection hides after 23:00.

**Snapshot capture**: new table `energy_snapshots(source_id, day, taken_at_local_min, total_kcal, active_kcal, steps)` (Alembic migration), written by each quick sync and by `/api/overview` refresh at most every 20 minutes; derived data, safe to drop, never needed for a rebuild. Garmin sync idempotence and rate limits unchanged (no new API calls).

**Target (`energy.target()`)**
- Maintenance estimate: median of last 28 settled days' `total_calories` if n >= 14 (trim days with active > 2x median: travel or races). Else if profile + weight exist: Mifflin-St Jeor resting x 1.4, labelled "formula guess, not measured". Else none ("Add height, birth date and sex in Settings to estimate" or "need 14 days").
- Optional weight-goal adjustment: if an active weight goal exists with a target date, desired pace = `(current - target) / weeks`, clamped to **at most 0.5% of body weight per week**; deficit/surplus = `pace x 7700 / 7` kcal/day, clamped to 15% of maintenance. Hide the adjustment when the goal is infeasible within the clamp and say so ("at a gentle pace this takes ~N weeks"). No adjustment during illness/injury/time off, and none for the first 3 weeks of a hard training block (plan state "overloading").
- Floor: never below the larger of 1,500 kcal or 1.1 x estimated resting burn; if the user types a lower value, accept it but show a neutral note ("Below your estimated resting burn; consider checking with a professional").
- User override in Settings (`energy_target`: mode auto|manual, manual kcal, eat-back %, pace on/off). Stored as `AppSetting`.
- Protein companion line: g/kg from weight (cited, 1.4 to 2.0 g/kg for training, ISSN position stand), shown only if weight known; never a medical claim.

**Wording rules**: no "burn it off", "earned", "cheat", "over/under budget in red". Use "so far", "about", "around", "estimated". Colour: remaining uses neutral/sky; going past the target is amber at most, never coral, and text stays factual ("About 180 above your estimate today; one day doesn't matter"). Footer on the card: "Garmin burn and food-log kcal are both estimates; individual error can be 10 to 20%+. Trends over weeks mean more than any day." No causal or medical claims. Show n: "typical for this time, 14 days".

**Payload addition** `energy: {status: ok|partial|insufficient|no_garmin_kcal, day, as_of_min, burned: {total, active, resting, as_of}, eaten: {kcal|null, logged: bool, entries, protein_g}, projected: {value, lo, hi, n, method: curve|fallback}|null, target: {kcal, source: manual|history|formula, adjustment_kcal, floor_applied, n_days}|null, left: kcal|null, workout_active_kcal, eat_back_pct, balance: {so_far_kcal}|null, spark: [{day,total,eaten}] x14}`.

**Tests** (`tests/test_energy.py`, synthetic): project with 12 curve days (range ordering, n shown); fallback at 8 days; insufficient at 6; empty food log gives `left=None`, `eaten.logged=False`; floor applied; pace clamp 0.5%/week; no adjustment on time-off day; outlier trimming; midnight rollover (burn resets, 00:05 shows "Today just started"); zero kcal (Garmin 0 at 00:01) treated as missing; assemble() purity (no DB).

## C. Day-phase engine (`analytics/dayphase.py`, pure)

`phase(now_local, day: DayFacts) -> {phase, flags, cards: [ids ordered], copy: {...}}`. `DayFacts`: sessions done (age of last end), planned session (kind, status), readiness, time-off kind, wellbeing (illness, pain, soreness), race date, steps and step goal, sleep recap, food logged, tonight target. `context()` loads, `assemble()` is pure; wording in `notes.py` consumes the phase.

**Time bands (user timezone)**: early 04:00-06:59 (`dawn`), morning 07:00-11:29, midday 11:30-14:29, afternoon 14:30-17:59, evening 18:00-20:59, late 21:00-03:59. **Overrides** (priority order): `sick` > `time_off` (travel/holiday/injury) > `race_day` / `race_week` > `post_workout` (a session ended <3 h ago, or done today and now < 21:00) > `rest_day` > time band.

| Phase | Hero/Now says | Hides or demotes |
| --- | --- | --- |
| morning | Readiness, today's plan, sleep recap (hours, score, HRV vs baseline), check-in prompt | evening sleep tips, "protein check" |
| midday | Plan status (not yet done / done), fuel: kcal so far, step pace | sleep recap collapses to a tile |
| afternoon | Last good window for the session ("sessions after ~18:00 can cost sleep" only as cautious wording), steps if achievable | |
| evening | Wind-down: sleep target tonight and bedtime, tomorrow preview, protein/fuel check; weather for tomorrow | unfinished-session CTA |
| late (>=21:00) | One calm card: "Day's done. Sleep by 22:45 (aim 7.8 h)", tomorrow's plan | readiness dial dimmed (a morning metric), step prompts, calorie "left" (shows "Day total so far") |
| post_workout | "Nice work. Refuel: protein + carbs", recovery cost, cool-down tips, calorie card with workout burn | plan nags |
| rest_day | "Rest is the plan today" with what helps (sleep, walk) | plan/session CTA |
| race_week / race_day | taper note, race-day checklist (fuel, weather), no new-load prompts | stretch targets |
| time_off | "Time off: nothing is missed", ease-back preview, steps and sleep tiles only | week-vs-plan misses |
| sick | rest advice, hydration, "Return when symptoms are gone", no plan, no step goals | training, streaks, score deltas |

**Unfinished-session rules** (the bug): the status `open` is replaced by `deferred` from 20:00 (or when strain budget is used, or readiness < 55, or wellbeing says less): title "Not today", detail "Tomorrow's session is {X}" or "Rest is fine; the week still works" depending on plan slack. Before 20:00 `open` copy is allowed only if >= 2 h daylight/time remains for the session's duration, otherwise `window_closed`. At no time does the Home use "open" to mean "not done" after 20:00. Past midnight a new `day` starts; yesterday's misses vanish (the Week strip carries them).

**Step prompts** only when achievable: `remaining_steps / hours_left_to_21:30 <= 2500 steps/h` and phase not in sick/time_off/late; otherwise show steps as a plain tile without nudging.

**Test matrix** (parametrised, fake clock): times {05:30, 08:00, 12:00, 16:00, 19:30, 20:00, 22:00, 23:45, 00:10} x states {no session planned, planned not done, planned done, hard done 1 h ago, bonus session, rest day, sick, travel, race week, race day, low readiness, pain flag, no Garmin data yet} = 117 cases. Key assertions: 22:00 + planned not done never contains "open"; 22:00 + sick shows no training copy; 16:00 + sick shows rest; 00:10 shows yesterday's totals as the new day; post-workout beats rest-day label; missing sleep data shows "sleep not synced yet", never 0 h; card order golden lists per phase; DST change day has no duplicate or missing band; user timezone differs from server.

## D. Layout at 375px

Gutter 20px (existing `px-5`), single column, `space-y-6` (reduce from 10). Order:
1. **Header (48px)**: weekday, date, sync chip; `PhaseHeader` greeting ("Good evening") with a one-line phase subtitle. Greeting shrinks from `text-5xl` to `text-3xl` serif to win ~60px.
2. **Vitals strip (96px tall tiles, 112px wide, swipeable, snap)**: Steps, Sleep, HRV, RHR, Body Battery, Stress (+ Weight, Floors after). Each tile: icon+label, bold num (28px), "vs usual" chip (60-day baseline, hidden under 14 points), 7-point sparkline. Taps go to `/metrics/:metric`. Missing value shows "not synced" dimmed, not 0. Phase can reorder (morning: Sleep, HRV, RHR first; evening: Steps, Stress, Body Battery).
3. **Calories hero card (about 240px)**: `CalorieRing` 168px with burn so far in the centre, an outer thin arc for projected range, eaten as inner arc; below it three stat cells (Eaten, Left, Projected), then a Log food button (44px) and one footnote line. Tap opens a Sheet with the breakdown, method, n, and target settings link.
4. **Now card** (phase-aware, replaces TodayCall/PlannedToday/StatusCard top parts): one primary action.
5. Readiness and Cadence score as a **compact pair** (two 96px dials; hidden/dimmed late) plus today's session.
6. Check-in / wellbeing (only when not done; collapsed to a chip when done).
7. Week strip and Recent sessions.
8. Collapsed under "More" (accordion): Today's read, Improve, What-if, Biggest gain, Streaks, Recovery wins, Strain, Weather (weather moves into Now when relevant).

**Remove**: the chip row (replaced by the Log food button on the calorie card and a FAB-less "+" in the header menu), the duplicate Vitals strip at the bottom, PhaseBanner folded into Now when active.

**Rationale**: glance first (state of the body, 3 s), then fuel (the user's stated goal), then act (what to do now), then plan, then explore. Facts before advice; things that rarely change go lowest.

## E. Visual direction

Keep the existing tokens (ink/coal/slate, cream, gold; lime, violet, coral, sky, amber, mint; Manrope + Instrument Serif + JetBrains Mono). The change is composition and energy, not a new palette.
- **Colour per domain**: Move/steps lime, Sleep violet, Heart/HRV mint, RHR coral, Energy (burn) amber, Intake sky, Body battery gold, Stress sky/dim. Defined once as `--color-domain-*` aliases in `index.css`; tile accent, sparkline, ring segments, and icon use the same alias. Never colour alone: every number has a label and a text delta.
- **Typography**: big numerals 40-56px `font-mono`/tabular (`num`) for hero, 28px for tiles; serif italic only for greeting and phase line. Units 12px `text-mute`.
- **Surfaces**: tiles get a 1px `line` border plus a faint domain gradient wash (domain colour at 6-8% over slate) and a 2px top accent; hero card gets a soft radial glow behind the ring.
- **Motion** (Framer Motion is already used: `stagger`/`rise`, `CountUp`): ring arcs animate stroke-dashoffset 600 ms with `--ease-snap`; numerals count up once per mount; the projection range arc fades in after; a live dot pulses on "so far" values (2 s loop). All of it gated by `prefers-reduced-motion` (reduce: no count-up, no arc sweep, static). No haptics.
- **Sparklines**: reuse `Sparkline` (28px); add an optional `baseline` prop (dashed usual line) and `highlightLast`.
- **Accessibility**: text contrast >= 4.5:1 on `slate` (mute #8d8a82 passes only large; use `paper` for numerals, `dim` only for non-essential), tap targets 44px (`pointer-coarse:` variants already used), ring has `role="img"` plus a text summary, tiles are links with readable labels, focus rings preserved, no information in colour alone.
- **States**: skeleton shimmer tiles (same size, so no layout jump), empty ("Nothing logged yet" with action), error (inline retry, last good value kept with "as of 14:05"), unsupported (Garmin kcal unavailable: "Your Garmin did not report calories"; demo source: labelled "Demo data").

**Reuse**: `Dial`/`MiniRing` (extract ring primitive), `Sparkline`, `CountUp`, `Sheet`, `VitalTile` (extend), `surface`, `chip`, `eyebrow`, `useWide`, `Chart` only inside Sheets.

**New components** (`app/web/src/components/home/`):
- `CalorieRing({ burned, active, resting, eaten, projected:{value,lo,hi}|null, target|null, size, state })`.
- `VitalTile({ metric, value, unit, baseline, deltaPct, spark, accent, to, state })`; `VitalsRail({ tiles, order })`.
- `PhaseHeader({ phase, greeting, subtitle, syncChip })`.
- `NowCard({ phase, copy, primaryAction })`.

### E2. What shipped (web, supersedes the "keep existing tokens" line above)

- **Identity**: "midnight and ember". Tokens live in `app/web/src/index.css` (`@theme` for dark, `:root[data-theme="light"]` and a no-script `prefers-color-scheme` fallback for light); `lib/theme.ts` holds the same palette for JS (charts, inline styles) as `C`. Token names are unchanged (ink = page, coal = card, slate = fill, cream = headings, paper = text) so every page flips together.
- **Palette (dark / light)**: ink #080a12 / #f5f3ee, card #10121d / #ffffff, text #eceef8 / #1c1e29, muted #9a9fbd / #555868. Domains: energy and calories gold (orange) #ff8a3d / #c2410c, activity lime #b8f53d / #3f7d00, sleep violet #a78bfa / #6741d9, recovery and HRV mint #38e8c0 / #00765f, heart coral #ff5d73 / #c81e48, intake and body sky #55b8ff / #0b64bd, stress and caution amber #ffc247 / #965800. Text accents are at least 4.5:1 on cards in both themes.
- **Type**: Manrope Variable (already bundled) at weight 800 with tight tracking replaces the serif display face (Instrument Serif imports removed, so slightly less payload); JetBrains Mono bold for numerals.
- **Shapes and depth**: 20px card radius, pill chips and buttons with a soft lift (the skewed NeoPOP edges are gone), card gradients and shadows tokenised (`--shadow-card`, `--face-top`, `--glow-*`).
- **Motion**: ring arcs sweep, sparklines draw, tiles rise in staggered, a live dot pulses on "so far"; all of it off under `prefers-reduced-motion`.
- **Theme choice**: default follows the device; Settings has Match device, Dark, Light, stored in `localStorage` (`cadence-theme`, try/catch) and applied by an inline script before first paint. Changing it reloads once so chart colours match.
- **Home**: header with phase accent, vitals rail, calorie hero card, phase-ordered cards (`lib/home.ts`), the rest under "More".

## F. Work breakdown (disjoint files)

**W1 Backend** (`analytics/energy.py`, `analytics/dayphase.py`, `models.py` + migration `energy_snapshots`, `insights.py` hooks, `main.py` overview payload, `notes.py` wording of `deferred/window_closed`, tests): energy projection/target, phase engine, snapshot writes, `/api/overview` gets `energy` and `phase`.
**W2 Web** (`pages/Overview.tsx`, new `components/home/*`, `Sparkline.tsx`, `index.css` domain aliases, `lib/types.ts`, `lib/home.ts` + tests): layout, vitals rail, CalorieRing, PhaseHeader/NowCard, motion, states.
**W3 Settings/copy** (`pages/Settings.tsx` energy section, `main.py` settings route `/api/settings/energy` plus share allowlist in `share.py`, copy strings file `lib/homeCopy.ts`, Coach page "How the coach works" entry, plan.md and README): target mode, eat-back, floor note, citations.

**Priority (MVP first)**
1. Phase engine + the 20:00 "deferred" fix (kills the visible bug; backend only).
2. Vitals rail moved to the top (web only, existing data).
3. Calories card v1: burn so far, eaten, left vs a manual or history target, no projection.
4. Snapshot table + projection with range (starts collecting immediately; ships when n >= 10).
5. Phase-aware Now card and ordering; collapse lower cards.
6. Visual pass: ring animations, domain colours, skeletons.
7. Weight-goal pace adjustment and settings polish.

**Risks**
- No intra-day history: the curve needs about 2 weeks of snapshots after shipping; the fallback is rougher. Start collecting first (step 4's table can ship with step 1).
- Garmin `burnedTotal` can lag the sync; Overview refreshes every 5 minutes but data may be minutes old; always show "as of".
- Calorie wording can slide into diet advice; floors, no-shaming copy, and the cautious cap on deficits are mandatory; no medical claims.
- Food-log under-logging makes "left" look generous; "nothing logged" is explicit, and a partial-day note after 18:00 ("only 2 entries logged") avoids false precision.
- Time zones and DST: use the user zone everywhere (`clock`); test it.
- Phone share server is read-only except an allowlist: the new energy setting must be added to it or phones cannot edit the target.
- Scope: the Home is large; moving cards must not drop features (all remain, reachable under "More").

## G. Implemented payload (backend, as built)

`GET /api/overview` keeps every existing field and adds `energy` and `phase` (only when `has_data` is true). All text lives in each block's `copy`; the web app should render those strings and never rebuild wording. Dates are ISO strings.

### `energy`

```json
{
  "status": "ok",                       // ok | partial | insufficient | no_garmin_kcal | just_started
  "day": "2026-10-22",
  "as_of_min": 840, "as_of": "14:00",   // local time of Garmin's value (its import time); null when no burn
  "burned": {"total": 1500, "active": 400, "resting": 1100, "as_of": "14:00"},   // null when Garmin has no kcal for today
  "eaten": {"kcal": 1200, "kcal_low": 1050, "kcal_high": 1350, "logged": true, "entries": 3, "protein_g": 70.0},
  "projected": {"value": 2419, "lo": 2381, "hi": 2475, "n": 14, "method": "curve"},   // method curve | fallback; null otherwise
  "projection_state": "ok",             // ok | partial | insufficient | hidden (after 23:00) | no_burn | null
  "projection_history_days": 14,
  "target": {"kcal": 2143, "source": "history", "maintenance_kcal": 2400, "adjustment_kcal": -257,
             "floor_kcal": 1980, "floor_applied": false, "below_floor": false, "n_days": 14,
             "pace": {"kcal": -257, "state": "on_pace", "kg_per_week": -0.23},   // state on_pace | gentle (+ weeks_at_gentle_pace) | at_goal; or null
             "hold": null,                                                       // time_off | unwell | hard_block | null (why the goal adjustment is paused)
             "protein": {"low_g": 112, "high_g": 160, "per_kg": [1.4, 2.0]}},    // null without a weight; whole target null when nothing to base it on
  "left": 1153, "above_by": null,       // left >= 0 or null; above_by only when past the estimate; both null when nothing is logged
  "workout_active_kcal": 420, "eat_back_pct": 50, "eat_back_kcal": 210,   // target already excludes eat_back; left includes it
  "balance": {"so_far_kcal": -300},     // eaten - burned so far; null unless both exist
  "spark": [{"day": "2026-10-09", "total": 2400.0, "eaten": null}, "...13 more...", {"day": "2026-10-22", "total": 1500.0, "eaten": 1200, "partial": true}],
  "yesterday": null,                    // {day, total, eaten} when status is just_started (before 01:00)
  "settings": {"mode": "auto", "manual_kcal": null, "eat_back_pct": 50, "pace": true},
  "copy": {"footnote": "...", "status": null, "burned": "...", "eaten": "Nothing logged yet | About N kcal logged", "target": "...", "left": "...",
           "projection": "...", "target_notes": ["..."], "workout": "...", "refuel": "...", "partial_log": null}
}
```

`target.source` is `manual | history | formula`. `target.kcal` is the base target; with a manual source `below_floor` may be true (show the neutral note in `copy.target_notes`). Missing is never zero: `eaten.kcal`, `burned`, `total` are `null` when unknown.

### `phase`

```json
{
  "phase": "late",    // dawn | morning | midday | afternoon | evening | late | post_workout | rest_day | race_week | race_day | time_off | sick
  "band": "late", "now_local": "22:00", "day": "2026-10-22",
  "flags": ["no_garmin_data", "sleep_not_synced", "low_readiness", "pain", "feeling_off", "strain_used", "new_day", "bonus", "food_logged"],
  "cards": ["now", "vitals", "calories", "week", "readiness", "more"],   // visible, in order; ids: vitals calories now readiness checkin week recent more
  "dimmed": ["readiness"], "hidden": ["checkin", "recent"],
  "vitals_order": ["steps", "stress", "body_battery", "sleep_hours", "hrv", "resting_hr"],   // overview metric keys
  "session_state": "deferred",   // none | rest | done | upcoming | open | window_closed | deferred | race
  "hints": {"phase": "late", "session": "deferred", "sleep": "tile", "calories": "day_total", "steps": "tile", "protein_check": false, "yesterday_recap": false},
  "copy": {"headline": "...", "session": {"title": "Not today", "detail": "..."}, "sleep": null, "calories": "Day total so far", "steps": null, "protein_check": null, "recap": null, "flags": ["..."]}
}
```

`hints.sleep` is `not_synced | recap | tile`; `hints.calories` is `left | day_total`; `hints.steps` is `prompt | tile`. `copy.session` is null when there is nothing to say (sick, time off).

### Settings and the 10 pm fix

- `GET /api/settings/calories` returns `{mode: auto|manual, manual_kcal, eat_back_pct, pace, ranges: {manual_kcal: [800, 6000], eat_back_pct: [0, 100]}, floor_kcal: 1500}`; `PUT /api/settings/calories` takes any subset (`mode`, `manual_kcal`, `eat_back_pct`, `pace`), validates (400/422 on bad values; manual mode needs a number) and returns the same shape. A paired phone may call the PUT.
- `coach.today` (from `notes.today_session`) gains `status: "deferred"` (title "Not today") and `"window_closed"` (title "Probably not today") for a session still to do, whether or not another session was done. From 20:00, or when the strain budget is used, readiness is under 55 or a check-in says less, it is `deferred`; from 18:00 it is at least `window_closed`; `open` is only used with 2 h or more left. `kind` is unchanged; use `status` for framing.

### Deviations from the design

- No `/api/settings/energy`; the route is `/api/settings/calories` (stored under `app_settings.energy_target`). No separate target-floor setting.
- Food entries have only a day (the `logged_at` is when it was logged, not eaten), so intake is a per-day sum.
- Extra statuses: `just_started` (before 01:00 burn is hidden and `yesterday` is given). `insufficient` is also used when burn exists but no projection can be made.
- Weight-goal pace: an over-ambitious goal is clamped (0.5% of body weight per week, 15% of maintenance) and flagged `state: "gentle"` with `weeks_at_gentle_pace`, rather than the adjustment being hidden. A goal without a date assumes a 12-week horizon.
- "Hard training block" is read as the weekly status `overloading` (a single-week signal), not a 3-week count.
- Snapshots are stamped with the time Garmin's value was imported (not the time of the request); they are recorded at the end of each sync and on overview refresh (when the value changed and at least 20 minutes passed). The curve needs 10 past days with a snapshot within 45 minutes of the same time, so it starts after about two weeks of use; until then the fallback (7+ settled days) is labelled rough.
- Step goal is not stored anywhere yet, so `hints.steps` is always `tile` until a goal is supplied.
