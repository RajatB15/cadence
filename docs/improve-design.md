# Improve: per-metric "what to start / what to watch" (HRV, VO2max, resting HR)

Status: design only. Citations were checked against PubMed/publisher/abstract records via web search (see "Verification log" at the end and `docs/improve-sources.json`); several were corrected. Items marked "not independently opened" in the log were only confirmed from bibliographic records. Effect sizes are ranges, not promises. Citation ids for the copy table are listed in the log.

## 1. What exists (survey)

**Metric page** (`app/web/src/pages/Metric.tsx`): `DayView`, `Trend` chart (30D/90D/1Y/All), `DayDetails`; fetches `/api/metrics/{metric}`. No interpretation or advice; the only guidance lives in `CoachNotes`/`MetricDayPanels`.

**Reusable backend**
- `analytics/athlete.py`: `compare()` (day-group contrast, covariate-adjusted OLS, lag-1 autocorrelation inflation, n_eff), `control_fdr()` (BH), `intensity_split()` (easy/moderate/hard % by time, hard sessions %), `sleep_pattern()` (debt, bedtime SD), `efficiency()`, `pmc()`, `baseline_z()`.
- `analytics/habits.py`: journal behaviours x {hrv, resting_hr, sleep_score, readiness, run_eff}, min 8 days each way, FDR. `insights.lagged_effects()`: load, sleep duration, bedtime, workout timing, stress, steps x HRV/RHR/sleep.
- `evidence.py` (VO2max, RHR, HRV, efficiency, CS, drift as independent markers with CI and practical floors; HRV+RHR count as one), `trends.py` (direction/outlook, Newey-West), `status.py` (progressing/overloading/deloading...), `fatigue_fit.py` (personal recovery speed), `channels.py` (easy vs hard minutes -> efficiency), `freshness.py`, `recovery.py` (`sleep_regularity` SRI, sleep need/tonight, HRV-guided), `heat.py`, `wellbeing.py`, `strain.py`, `body.py`, `plan.py`/`planner.py`/`timeoff.py`, `notes.py` (wording), `regress.ols` (Newey-West).
- `insights.assemble(c)` is the pure test seam; `coach(c)` is a flat rule list (`finding(id, severity, category, title, detail, action, evidence, link)`).

**Daily signals in `daily_metrics` (key names seen in importer/normalize)**: `hrv` (+ `hrv_weekly`, `hrv_balanced_low/high`, `hrv_intraday`), `resting_hr`, `sleep_hours`, `sleep_score`, `deep_sleep_h`, `rem_sleep_h`, `sleep_stress`, `bedtime`/`wake_time` (minutes from midnight), `stress`, `body_battery` (+`_low`, `_now`), `intensity_minutes`, `steps`, `respiration`/`respiration_rate`, `spo2`, `vo2max`, `hydration_ml`, `calories_consumed`, plus `weight_kg` (WeightReading, manual or scale). Activities: type, duration, avg/max HR, `training_load`, `aerobic_te`, zone seconds (`zones_s`), end time, weather (dew point/temp). Journal: alcohol (count), late caffeine, late meal, screens, sauna, stress, travel, ill, mobility, nap + custom. Wellbeing (feel, soreness, pain, illness, life stress), time off, food log with nutrients (only when logged), goals, weekly status.

**Cannot support (state in UI)**: causal claims; alcohol/caffeine/meal timing unless journalled (missing != no); hydration unless logged; sleep-stage values are device estimates; Garmin VO2max is an estimate (HR+pace model, weakened by heat/altitude/hilly or stop-start runs, GPS error, stale HRmax, wrist HR error) and moves in steps; SpO2/respiration are weak drivers here; no lab values; no menstrual-cycle or altitude data.

## 2. Evidence base (effect sizes and quality)

**HRV (RMSSD)**
- Measure as a rolling 7-day mean against your own baseline and coefficient of variation, not single nights: Plews et al. 2013 (Sports Med 43:773; Plews et al. 2014 IJSPP 9:1026-1032 "Heart-rate variability and training-intensity distribution in elite rowers", n=9: phases with more high-intensity work tended to lower parasympathetic indices, low-intensity work maintained or raised them). Quality: observational, small elite samples.
- Training load: HRV drops after hard/high-intensity days and recovers within 24-72 h; a sustained fall with rising RHR plus poor feel is a pattern worth a look, not a diagnosis (Buchheit 2014, Front Physiol 5:73, a methods review of HR-based monitoring; Meeusen et al. 2013, ECSS/ACSM consensus, MSSE 45:186, which states that no single marker is accepted for diagnosing overreaching/overtraining and stresses overload plus inadequate recovery). Evidence is observational and mostly in athletes. Stable or rising 7-day mean with low CV has been described alongside positive adaptation in elite athletes (Plews 2013).
- HRV-guided training is at most marginally better than fixed plans for fitness: Kiviniemi et al. 2007 (EJAP 101:743; 26 men, no significant between-group difference in VO2peak change); Vesterinen et al. 2016 (MSSE 48:1347; 40 recreational runners, VO2max improved in both groups, 3.7% guided vs 5.0% predefined, with fewer hard sessions in the guided group and a small 3000 m advantage); meta-analysis Manresa-Rocamora et al. 2021 (Int J Environ Res Public Health 18:10299; VO2max SMD 0.20, 95% CI -0.07 to 0.47, not significant; vagal HRV indices SMD 0.50). Treat as "similar fitness with fewer hard sessions", low-moderate quality.
- Alcohol: dose-dependent drop in HRV-derived parasympathetic and recovery measures over the first hours of sleep (Pietila et al. 2018, JMIR Ment Health 5:e23; 4,098 working-age adults compared within person on drinking vs non-drinking days, observational; the recovery measure fell about 9, 24 and 39 percentage units at low, moderate and high intake). Spaak et al. 2010 (Am J Physiol Heart Circ Physiol 298:H2226; 12 adults, randomised crossover): one drink had no effect, two drinks raised heart rate about 5 bpm and lowered HF power.
- Sleep: HRV varies with sleep stage and sleep disorders (Stein & Pu 2012, Sleep Med Rev 16:47-66, a review; it does not establish an effect size for next-day HRV after short sleep, so none is claimed here). Sleep regularity: Phillips et al. 2017 (Sci Rep 7:3216) introduced the Sleep Regularity Index in 61 students (regularity related to circadian timing and grades, similar duration); Windred et al. 2024 (Sleep 47:zsad253; 60,977 UK Biobank adults, observational) found regularity a stronger predictor of all-cause mortality than duration. Neither studied HRV or RHR; evidence for HRV specifically is low.
- Illness: resting HR elevations relative to personal baseline preceded or coincided with symptoms in some COVID-19 cases in smartwatch data (Mishra et al. 2020, Nat Biomed Eng 4:1208; 32 cases, 63% detectable pre-symptomatically by a retrospective RHR rule); population-level Fitbit resting HR and sleep signals improved state-level influenza-like-illness estimates (Radin et al. 2020, Lancet Digit Health 2:e85). Neither paper establishes an HRV fall or an individual-level threshold. Population/small-sample signal, not individual diagnosis.
- Late meals, caffeine, hydration, travel: smaller or less consistent; no citation is given for late meals (rely only on the user's own journal); jet lag and time-zone shifts cause sleep loss and reduced performance (Waterhouse et al. 2007, Lancet 369:1117-1129 review; not HRV-specific). Stress: psychological stress is associated with lower parasympathetic HRV in a review of 37 studies (Kim et al. 2018, Psychiatry Investig 15:235-245).
- Day-to-day HRV noise is large, which is why a rolling mean and personal band are used (Plews 2013; Buchheit 2014). Smartphone RMSSD monitoring in a female soccer team used the CV of log RMSSD as an adaptation marker (Flatt & Esco 2016, J Strength Cond Res 30:378-385). No population CV range is claimed.

**Resting HR**
- Regular endurance exercise lowers RHR in healthy people (Reimers et al. 2018, J Clin Med 7:503, meta-analysis of 191 studies; the drop is larger with higher starting RHR and younger age; the exact bpm range is not asserted here). Detraining reverses adaptations over weeks (Mujika & Padilla 2000, Sports Med 30:79-87 and 30:145-154). Smaller effect in already-trained people is a reasonable expectation, not a cited result.
- Short-term elevations: acute illness/fever, heat, dehydration, alcohol (Spaak 2010: +5 bpm after two drinks in 12 adults), sleep deprivation (small), residual fatigue (see Meeusen 2013 on overload without recovery). The "+5 bpm over baseline" and "+3 bpm" cut-offs in section 3(c) are Cadence design heuristics, not published thresholds; Mishra 2020 used extreme deviations from each person's own baseline.
- Higher RHR associates with mortality risk across populations (Aune et al. 2017, Nutr Metab Cardiovasc Dis 27:504-517: RR 1.17 all-cause per 10 bpm; Zhang et al. 2016 CMAJ 188:E53-E63: RR 1.09 per 10 bpm), observational: context only.

**VO2max**
- Interval training elicits somewhat larger VO2max gains than moderate continuous work: Milanovic et al. 2015 (Sports Med 45:1469-1481; 28 studies, 723 participants, mean age ~25): HIT 5.5 vs endurance 4.9 mL/kg/min vs controls, and HIT +1.2 mL/kg/min (+/-0.9) over endurance training ("possibly small"). Bacon et al. 2013 (PLoS One 8:e73182; 37 studies, 334 subjects, 6-13 weeks) reports interval training gains in absolute VO2max (up to ~1.0 L/min in some studies, pooled ~0.5 L/min); it does not give a per-kg comparison with continuous training, so no such figure is claimed. Moderate quality, mostly young, untrained/recreational.
- 4 x 4 min interval protocol (target about 90-95% HRmax, not re-verified from the paper text): Helgerud et al. 2007 (MSSE 39:665-671; 40 moderately trained men, 8 weeks, 3 sessions/week) reported VO2max +7.2% in the 4x4 group, more than long slow distance or threshold work. Wisloff et al. 2007 (Circulation 115:3086-3094) was a randomised trial in 27 post-infarction heart-failure patients (VO2peak +46% interval vs +14% moderate); it is NOT evidence for healthy recreational adults and is not used for effect sizes.
- Polarized/80-20: Seiler & Kjerland 2006 (Scand J Med Sci Sports 16:49), Seiler 2010 (IJSPP 5:276-291; observational review: elite endurance athletes do roughly 80% of sessions/time at low intensity); Stoggl & Sperlich 2014 (Front Physiol 5:33) polarized beat threshold/high-volume/high-intensity groups in 48 well-trained endurance athletes over 9 weeks (VO2peak +11.7% polarized; the +4.8% HIT-only figure was not re-verified); Rosenblat et al. 2019 (J Strength Cond Res 33:3491-3500) meta-analysis of only 4 trials (3 pooled, PEDro 4-5/10): time-trial performance favoured polarized over threshold (ES -0.66, 95% CI -1.17 to -0.15), preliminary. Quality: low-moderate; do not claim superiority, state as "many coaches and some small trials favour".
- Volume and frequency: more weekly aerobic volume correlates with higher VO2max in trained groups; for recreational runners 3-5 sessions/week with 1-2 hard is usual practice (Laursen & Jenkins 2002, Sports Med 32:53-73 on interval structure in trained athletes; Midgley, McNaughton & Wilkinson 2006, Sports Med 36:117-132, "Is there an optimal training intensity for enhancing the maximal oxygen uptake of distance runners?"). Evidence: expert review plus moderate studies; the 3-5 sessions/week figure is common practice, not a cited result.
- Training near VO2max may be the most effective intensity for raising VO2max in moderately trained runners (Midgley 2006); the broader point that other determinants of running performance (threshold, economy) respond to different work is in Midgley, McNaughton & Jones 2007 (Sports Med 37:857-880). The earlier claim that threshold work beats VO2max work, and the "Daniels 2013" reference, are removed as unsupported.
- Body mass: VO2max in mL/kg/min rises mechanically when mass falls at same absolute VO2; lean mass drives absolute VO2max. Garmin's number uses user weight as input.
- How Garmin/Firstbeat estimate VO2max: from HR vs speed (running/walking with GPS) using a regression between HR fraction of reserve and speed, corrected for HR drift/speed variation; needs HRmax/resting HR and weight; heat and altitude acclimation corrections are applied on newer devices (Firstbeat's published description of its fitness-level method and white papers at firstbeat.com; the exact 2014 white paper title/PDF could not be retrieved, so quote the method generically and link the Firstbeat science page; Garmin Support "VO2 Max"). Validation: Molina-Garcia et al. 2022 (Sports Med 52:1577-1597, meta-analysis of 14 studies) found small population-level bias (about -0.1 mL/kg/min for exercise-based algorithms) but wide individual limits of agreement (roughly +/-10 mL/kg/min); Passler et al. 2019 (Int J Environ Res Public Health 16:3037, n=24) found MAPE 7.3% for the Garmin Forerunner 920XT VO2max and >10% for other wrist devices. The earlier "typical error +/-5%" is removed. Changes under ~2-3 mL/kg/min over weeks should be treated as possibly noise: this is a conservative Cadence design heuristic, not a published threshold; label it an estimate.

**Normative context (display only)**: Cooper Institute/ACSM (Liguori 2021, ACSM Guidelines 11th ed.) percentile tables by age and sex; FRIEND registry treadmill percentiles: use the 2022 update (Kaminsky et al., Mayo Clin Proc 97:285-293; 22,379 tests; treadmill standards are 1.5-4.6 mL/kg/min lower than the 2015 set, Kaminsky et al. Mayo Clin Proc 90:1515-1523, which should not be used for new tables); HUNT3 fitness reference data: Loe et al. 2014 (PLoS One, "Cardio-respiratory reference data in 4631 healthy men and women 20-90 years: the HUNT 3 fitness study"; replaces the earlier "Nes 2011 MSSE 43:1849" reference, which was wrong and is a different paper). RHR: Ostchega et al. 2011 (NHANES 1999-2008, Natl Health Stat Report 41; 47,610 participants) for survey percentiles; Quer et al. 2020 (PLOS ONE 15:e0227709, 92,457 Fitbit users) describes how widely wearable RHR varies between people (up to ~70 bpm) rather than giving norm tables, so use it only for the "ranges are wide, personal baseline dominates" note. HRV: Nunan et al. 2010 (PACE 33:1407) population RMSSD ranges; Shaffer & Ginsberg 2017 (Front Public Health 5:258); emphasise that HRV normals are very wide and age falls with age, so personal baseline dominates.

## 3. Design

All Improve output is **association on your own history, never causal or medical**. Everything is missing-aware: a day without a value is skipped, not zero.

### (a) What is moving it (driver analysis) - `analytics/drivers.py` (pure)
For target T in {hrv, resting_hr, vo2max}. Reuse `athlete.compare`, `habits.insights`, `regress.ols`, `control_fdr`; do not duplicate.
- Candidate exposures (computed in `insights.py` loader as `exposure series`, 0-lag and 1-2 day lag): sleep hours (7-day mean, short nights), bedtime SD / SRI, alcohol 2+ drinks (journal), late meal/caffeine/screens/travel (journal), prior-day load and 7-day load, hard-session count in 7 days, easy-share of minutes (28 days), intensity minutes, steps, daytime stress, evening workouts, heat (journal sauna / dew point), time off, illness.
- Method per exposure: day-group contrast via `compare()` (adjusted for same-day load and weekend; Newey-West-style n_eff inflation already inside) or, for continuous exposures, `regress.ols` with `lags=7` of T(t+lag) on exposure(t) plus load and trend, with standardised coefficient and 95% CI. For vo2max (sparse, step-like), use weekly aggregates over 12+ weeks, Spearman with permutation p (block permutation, blocks of 7 days, 2,000 shuffles) and effect expressed as change per +1 SD with a bootstrap (block) CI.
- Min data: group n >= 8 each way (existing), 40+ days of target overlap, 6+ weeks for weekly regressions, 12+ weeks and 6+ vo2max readings for vo2max. Below min: show a progress bar "need N more nights" (like `habits.progress`).
- Multiplicity: BH across all tests for that target (q < 0.05 = "clear", q < 0.2 = "hint", else not shown except in "all tested" list). Show n, n_eff, effect in native unit and as % of baseline, CI, q. Always the label "association, not proof".
- Output ranked by |standardised effect| among q-clear; max 5 shown.

### (b) What to start - `analytics/improve_rules.py` (pure)
Each rule is a function `(ctx) -> Recommendation | None`, ctx from `insights.assemble` plus drivers. Fields: `id, metric_tags, finding, numbers{value,n,window_days}, why (text+citation_ids), action, timescale, confidence (low/med/high from n and CI), ease (1-3), impact (1-3), safety_note`.
Rules (MVP marked *):
1. * Intensity distribution: easy share by time over 28 days < 70% or moderate > 25% (`intensity_split`; min 6 sessions, 180 min) -> "Make easy days easier: keep easy runs in zone 1-2." Timescale 4-8 weeks. Cite Seiler 2010, Stoggl 2014 (with the weak-evidence caveat).
2. * Too few hard sessions: hard sessions < 1 per week averaged over 4 weeks while at least 3 sessions/week and VO2max/efficiency flat -> one structured interval session (e.g. 4 x 4 min at zone 4-5 effort); builds on `plan.py` key sessions. Helgerud 2007, Milanovic 2015. 6-12 weeks. VO2max tag.
3. * Too many hard sessions: hard share > 25% of sessions or 3+ hard days in a rolling week, with HRV 7-day mean below baseline band -> swap one hard for easy. Meeusen 2013, Plews 2014.
4. * Sleep duration/regularity: 14-day mean below personal need by > 45 min, or bedtime SD > 60 min / SRI low (`sleep_pattern`, `sleep_regularity`) -> fix wake time first. Phillips 2017. 2-4 weeks for HRV/RHR signal.
5. * Alcohol nights: personal HRV/RHR effect is q-clear and 2+ drink nights >= 8 -> "On nights with 2+ drinks your HRV averaged X lower (CI) - consider alcohol-free nights before key sessions." If journal incomplete, say so.
6. Easy-day HR too high: avg HR on easy-labelled runs above zone-2 ceiling in > 50% of runs (n >= 8) and `channels`/efficiency flat. Action: slow down, walk breaks, use HR cap. 4 weeks.
7. Volume/frequency: 4-week average weekly minutes flat or fallen > 20% with no time off; propose +10% (never beyond `plan.py` ramp caps).
8. No recovery weeks: >= 5 consecutive weeks building without a deload week (`status.py`) -> insert a deload (plan 3:1).
9. Long gaps: >= 7 consecutive days without activity outside logged time off -> restart ramp (uses `timeoff.py` ease-back rules). Detraining: Mujika & Padilla 2000.
10. Late meal / evening workouts / screens: only when q-clear in the user's own data.
11. VO2max context: weight change > 3% in 8 weeks explains part of the mL/kg shift; heat runs (dew point > 18) depress estimate; show "heat adjusted" note when >= 50% of recent qualifying runs warm.
12. RHR: no aerobic base - fewer than 150 min/week easy aerobic for 4 weeks -> add easy minutes.

### (c) What to stop / watch - `analytics/improve_watch.py` (pure)
Prompts-to-look, wording "worth a look". Never disease names. Triggers (all need 14+ nights baseline):
- Overreaching pattern: 7-day HRV mean below baseline band (personal mean +/- 0.75 SD of 60 days) for >= 5 of 7 days AND RHR 7-day mean >= +3 bpm AND (load 7d above 28d mean x1.2 or feel <= 2). Evidence: Plews 2013, Meeusen 2013.
- Sleep debt streak: >= 4 nights below need - 1 h.
- Illness signature: RHR >= +5 bpm over baseline and HRV <= -20% for 2+ nights, or logged illness/run-down. Message: "your overnight numbers look unusually off; consider an easy day and see how you feel; if you feel unwell or symptoms persist, speak to a clinician." (Mishra 2020).
- Detraining: 10+ days without aerobic work and RHR trending up.
- Suppressed HRV with low CV for weeks (Plews: parasympathetic saturation in some athletes): shown only as "unusual; check with how you feel", low confidence.
Each shows numbers, n, window, and links to the day in question. Suppress when time off covers the period (no "miss").

### (d) 4-week focus plan - `analytics/focus.py` (pure)
Input: recommendations, drivers, watch flags, plan caps. Score = impact x confidence x ease (1-3 each; confidence from n/CI). Take top 3 with distinct domains (sleep, intensity, volume, recovery, alcohol). Watch flags of severity "act" override: focus becomes "recover first" and max 1 priority. Output per priority: title, target metric(s), weekly measurable behaviour (e.g. "4 nights/week asleep by 23:30"), check date (28 days), what would count as success (range, not a promise).
Planner integration: focus produces *suggestions only* (e.g. `intensity_bias: easier`, `add_key_session: vo2`, `deload_week: true`) consumed by `plan.py`/`planner.py` through an optional `focus` input that can only *reduce* or keep load constraints; any "add session" is clamped by existing ramp caps, long-run +10% rule, time off, wellbeing, and watch flags. Stored in a new table `focus_plans` (id, start, end, priorities JSON, baseline JSON, status) via Alembic migration; user accepts/dismisses; nothing automatic.

### (e) Tracking - `analytics/focus_review.py` (pure)
After >= 28 days (min 14 days of data per window and 60% adherence signal where measurable): compare target metric mean/trend in the focus window vs the previous equal window with a Welch-type interval using Newey-West variance (`regress.ols` with a step dummy and linear trend, lags=7), report change with 95% CI as "the 4 weeks after you started X: HRV average was 4 ms higher (range -1 to +9, n=26 vs 27 nights)". Context lines: load change, time off, illness days, weather. Verdict words only "higher / lower / no clear change". Never "it worked".

### (f) Benchmarks - `analytics/norms.py` (pure, static tables)
Inputs: age, sex from `profile.py` (missing -> hide, with "add profile" prompt). Output: percentile band (e.g. "Fair / Good / Excellent" Cooper/ACSM) for VO2max; FRIEND percentile for treadmill-measured values with the note that wearable estimates differ; RHR distribution band by age/sex; HRV: personal baseline band first (mean, SD, 7-day CV), population range second with large "ranges are wide; age and device differ". Shown as small grey context with citation, never colored good/bad. Tables are public published values keyed with source ids; they must be transcribed from the papers with tests asserting monotonicity and boundaries.

## 4. API

`GET /api/improve/{metric}` where metric in `hrv|vo2max|resting_hr` (read-only; allowed on the phone server as a GET). `GET /api/improve` returns summary for Home. `POST /api/focus` (accept), `POST /api/focus/{id}/dismiss` -> add `/api/focus*` to the phone write allowlist in `share.py` only if the phone should accept focus; MVP: read-only on phone.

```json
{
  "metric": "hrv", "as_of": "2026-11-08", "state": "ready|collecting|unsupported|error",
  "baseline": {"mean": 62.0, "sd": 8.1, "cv_7d": 9.4, "band": [56, 68], "n": 58, "window_days": 60, "unit": "ms"},
  "trend": {"direction": "up|down|steady|too_early", "change": 3.1, "ci": [-0.5, 6.7], "n": 84},
  "data": {"nights": 58, "needed": 40, "missing_signals": ["alcohol (journal)", "hydration"]},
  "drivers": [{"id": "alcohol_hrv", "exposure": "2+ drinks", "reference": "no drinks", "lag_days": 1,
     "diff": -7.4, "unit": "ms", "pct": -11.9, "ci": [-12.1, -2.7], "n_exposed": 9, "n_reference": 41,
     "n_effective": 31.2, "q": 0.03, "grade": "clear|hint", "adjusted_for": ["training load","weekend"],
     "note": "Association in your data, not proof."}],
  "progress": [{"key":"late_meal","have":4,"needed":8}],
  "start": [{"id":"easy_share_low","finding":"...","numbers":{"easy_pct":58,"target_pct":80,"minutes":412,"sessions":9,"window_days":28},
     "why":"...","citations":["seiler2010","stoggl2014"],"action":"...","timescale":"4-8 weeks",
     "impact":3,"confidence":2,"ease":2,"score":12,"tags":["hrv","vo2max"]}],
  "watch": [{"id":"overreach_pattern","severity":"look|act","title":"Worth a look","numbers":{},"citations":[],"suggestion":"..."}],
  "focus": {"id":null,"proposed":true,"start":"2026-11-09","check_on":"2026-12-07","priorities":[{"rank":1,"title":"...","behaviour":"...","target_metrics":["hrv"],"planner_hint":{"intensity_bias":"easier"}}],"blocked_by":null},
  "review": {"focus_id":3,"window":{"n_before":27,"n_after":26},"change":4.1,"ci":[-1.0,9.2],"unit":"ms","verdict":"no_clear_change|higher|lower","context":["Load +12%","2 illness days"]},
  "benchmarks": {"vo2max":{"value":47,"band":"Good","percentile":[60,70],"source":"acsm_cooper","estimate":true}, "profile_missing":false},
  "methods": ["plews2013","seiler2010"]
}
```
`state:"collecting"` returns progress and no advice; `unsupported` when no data for that metric (e.g. no HRV from device).

## 5. Wording rules (non-causal templates)
- Data statement: "On {n_exposed} {exposed} (vs {n_ref} {reference}) your {outcome} was {x} {unit} {higher|lower} (95% range {a} to {b}). This is an association in your own history, not proof."
- Suggestion: "Worth trying for 4 weeks: {action}. People in studies often see {range} over {timescale}; your own result may differ."
- Watch: "Your {signal} has been {x} for {k} days. That is worth a look: how do you feel? {safe action}. This is not a diagnosis."
- Forbidden: "causes", "because of", "proves", "you have/are", "overtrained", "sick", disease names, "will improve". Allowed: "tends to", "was lower on", "may", "worth a look". Never colour a benchmark as pass/fail. Garmin VO2max always "Garmin's estimate". Include sample size beside every number. If confidence low say "early, based on {n} nights".

## 6. UI
- **Metric page**: new "Improve" section under `Trend` (tabs or anchor): cards in order: Baseline strip (band chart + 7-day mean + CV), Focus card (top), Start list (max 3 expanded, rest collapsible), Watch card (only when triggered, top of section), What is moving it (effects list with CI bars + "association" chip), Benchmarks (collapsed, grey), Last focus review. Phone: single column, cards full width, 16px gutters, tap targets 44px, CI bars as horizontal ranges with text alternative.
- **States**: loading skeletons; error with retry; collecting (progress bars "12 of 40 nights"); empty ("no data for this metric yet"); unsupported ("your device does not report HRV"); partial (missing journal -> "log alcohol to see this" link to Journal); READ_ONLY phone hides accept/dismiss.
- **Home (Overview)**: one "Focus this month" card with top priority and check date; watch flag chip when active.
- **Coach page**: "How the coach works" gets methods entries per rule with citations; coach findings link to Improve.

## 7. Tests (synthetic only; no `data/`)
Fixtures in `tests/fake_garmin.py`-style builders: `synthetic_series(days, hrv_base, noise, ar1, effects={...})`.
- drivers: planted alcohol effect (-8 ms, 12 nights) is recovered, CI contains truth, q<0.05; null data yields no clear driver across 200 seeds (false-positive rate <= ~10% at q 0.05); autocorrelated noise does not inflate; missing days are skipped not zero; below min n -> progress only.
- rules: each rule fires on a crafted case and not on its complement; boundary tests (exactly min n); time-off windows suppress watch flags.
- watch: overreach pattern fixture (load spike then HRV fall and RHR rise) fires `look`; illness fixture wording check (no forbidden words via regex over all templates).
- focus: ranking determinism; max 3; watch override; planner hint cannot raise targets above `plan.py` caps (integration test).
- review: planted +5 ms step recovered with CI; no change case returns `no_clear_change`.
- norms: monotonic table tests, age/sex boundaries, missing profile.
- API: schema test, `collecting/unsupported/ready` states, phone-share read-only check.
- Frontend (Vitest): formatters, state rendering, forbidden-word test on copy constants.

## 8. Work breakdown (disjoint files)

**WS1 Backend** (`analytics/drivers.py`, `improve_rules.py`, `improve_watch.py`, `focus.py`, `focus_review.py`, `norms.py`, `focus_store.py`, migration, `insights.py` hook `improve(c, metric)`, `main.py` routes, `share.py` GET allowance, backend tests). Template ids and copy keys come from WS3; until delivered use ids only.
**WS2 Web UI** (`app/web/src/components/Improve*.tsx`, `pages/Metric.tsx` section, `pages/Overview.tsx` card, `lib/api.ts`/`types.ts` for the new payload, Vitest). Codes against the JSON above (mock fixture).
**WS3 Copy/methods** (`analytics/improve_copy.py` templates + citation table, `app/web/src/lib/improveCopy.ts` mirror or served in payload, "How the coach works" section in `Coach.tsx` excluding other edits, README methods, forbidden-word test, citation verification). Citations table ids: seiler2010, stoggl2014, plews2013, plews2014, buchheit2014, meeusen2013, kiviniemi2007, helgerud2007, milanovic2015, pietila2018, mishra2020, phillips2017, mujika2000, firstbeat2014, kaminsky2015, liguori2021.

**Priority order (MVP first)**
1. Payload skeleton + baseline + states (WS1/WS2).
2. Rules 1-5 (intensity, hard count, sleep, alcohol) + watch overreach/illness/sleep debt (WS1), copy (WS3).
3. Driver analysis with FDR using existing `compare` (WS1), UI list.
4. Focus card + manual accept (WS1/2), planner hints.
5. Review tracking, then benchmarks, then rules 6-12 and VO2max weekly permutation analysis.

## Sources
Corrected reference list (see Verification log). Plews DJ et al. 2013 Sports Med 43:773-781. Plews DJ et al. 2014 IJSPP 9:1026-1032. Buchheit M 2014 Front Physiol 5:73. Meeusen R et al. 2013 MSSE 45:186-205. Kiviniemi AM et al. 2007 Eur J Appl Physiol 101:743-751. Vesterinen V et al. 2016 MSSE 48:1347-1354. Manresa-Rocamora A et al. 2021 IJERPH 18:10299. Flatt AA, Esco MR 2016 J Strength Cond Res 30:378-385. Pietila J et al. 2018 JMIR Ment Health 5:e23. Spaak J et al. 2010 Am J Physiol Heart Circ Physiol 298:H2226-H2231. Phillips AJK et al. 2017 Sci Rep 7:3216. Windred DP et al. 2024 Sleep 47:zsad253. Stein PK, Pu Y 2012 Sleep Med Rev 16:47-66. Kim HG et al. 2018 Psychiatry Investig 15:235-245. Mishra T et al. 2020 Nat Biomed Eng 4:1208-1220. Radin JM et al. 2020 Lancet Digit Health 2:e85. Waterhouse J et al. 2007 Lancet 369:1117-1129. Seiler KS, Kjerland GO 2006 Scand J Med Sci Sports 16:49. Seiler S 2010 IJSPP 5:276-291. Stoggl T, Sperlich B 2014 Front Physiol 5:33. Rosenblat MA et al. 2019 J Strength Cond Res 33:3491-3500. Helgerud J et al. 2007 MSSE 39:665-671. Wisloff U et al. 2007 Circulation 115:3086-3094 (heart-failure patients). Milanovic Z et al. 2015 Sports Med 45:1469-1481. Bacon AP et al. 2013 PLoS One 8:e73182. Laursen PB, Jenkins DG 2002 Sports Med 32:53-73. Midgley AW et al. 2006 Sports Med 36:117-132. Midgley AW et al. 2007 Sports Med 37:857-880. Mujika I, Padilla S 2000 Sports Med 30:79-87, 145-154. Reimers AK et al. 2018 J Clin Med 7:503. Hellsten Y, Nyberg M 2016 Compr Physiol 6:1-32. Aune D et al. 2017 Nutr Metab Cardiovasc Dis 27:504-517. Zhang D et al. 2016 CMAJ 188:E53-E63. Firstbeat fitness-level method (firstbeat.com; white paper not retrieved). Molina-Garcia P et al. 2022 Sports Med 52:1577-1597. Passler S et al. 2019 IJERPH 16:3037. Kaminsky LA et al. 2015 Mayo Clin Proc 90:1515-1523. Kaminsky LA et al. 2022 Mayo Clin Proc 97:285-293. Liguori G (ed.) 2021 ACSM Guidelines 11th ed. Loe H et al. 2014 PLoS One (HUNT3 reference data). Ostchega Y et al. 2011 Natl Health Stat Report 41. Quer G et al. 2020 PLOS ONE 15:e0227709. Nunan D et al. 2010 PACE 33:1407-1417. Shaffer F, Ginsberg JP 2017 Front Public Health 5:258. Newey WK, West KD 1987 Econometrica 55:703. Benjamini Y, Hochberg Y 1995 JRSS-B 57:289.
Citation ids for WS3 (unchanged): seiler2010, stoggl2014, plews2013, plews2014, buchheit2014, meeusen2013, kiviniemi2007, helgerud2007, milanovic2015, pietila2018, mishra2020, phillips2017, mujika2000, firstbeat2014, kaminsky2015, liguori2021. Note for WS3: kaminsky2015 is superseded for table values by kaminsky2022; firstbeat2014 should cite the Firstbeat science page, not a specific white paper title; helgerud2007 is the only 4x4 source (wisloff2007 is heart failure and must not be cited for healthy adults).

## Verification log
Checked via web search of PubMed/publisher/repository records (abstract level; full texts were generally not opened). Machine-readable copy: `docs/improve-sources.json`.

| Reference | Status | URL | Note |
| --- | --- | --- | --- |
| Plews 2013 Sports Med 43:773 | VERIFIED | https://doi.org/10.1007/s40279-013-0071-8 | Specific findings only confirmed at abstract level |
| Plews 2014 IJSPP | CORRECTED | https://doi.org/10.1123/ijspp.2013-0497 | Pages 9(6):1026-1032, not 9:1-6; n=9 rowers |
| Buchheit 2014 Front Physiol 5:73 | VERIFIED | https://pubmed.ncbi.nlm.nih.gov/24578692/ | Methods review of HR measures; claim reworded |
| Meeusen 2013 MSSE 45:186 | CORRECTED | https://pubmed.ncbi.nlm.nih.gov/23247672/ | Consensus says no single marker diagnoses overtraining; claim downgraded |
| Kiviniemi 2007 EJAP 101:743 | CORRECTED | https://pubmed.ncbi.nlm.nih.gov/17849143/ | No significant between-group VO2peak difference in abstract |
| Vesterinen 2016 MSSE 48:1347 | CORRECTED | https://pubmed.ncbi.nlm.nih.gov/26909534/ | VO2max improved in both groups (3.7% vs 5.0%); no advantage |
| Manresa-Rocamora 2021 | CORRECTED | https://doi.org/10.3390/ijerph181910299 | IJERPH 18:10299 (not 10041); VO2max SMD 0.20 (-0.07 to 0.47), not significant |
| Flatt & Esco 2016 | CORRECTED | https://scholars.georgiasouthern.edu/en/publications/evaluating-individual-training-adaptation-with-smartphone-derived/ | J Strength Cond Res 30(2):378-385 (not 30:2564); "CV 5-15%" claim removed |
| Pietila 2018 JMIR Ment Health 5:e23 | VERIFIED | https://doi.org/10.2196/mental.9519 | 4,098 subjects (not "36 adults"); wording fixed |
| Spaak 2010 | VERIFIED | https://pubmed.ncbi.nlm.nih.gov/20418480/ | Am J Physiol Heart Circ Physiol 298:H2226; 12 adults |
| Stein & Pu 2012 | CORRECTED | https://pubmed.ncbi.nlm.nih.gov/21658979/ | Real review, but does not support "next-day HRV falls after short sleep"; claim removed |
| Phillips 2017 Sci Rep 7:3216 | CORRECTED | https://doi.org/10.1038/s41598-017-03171-4 | 61 students, SRI introduced; not evidence of health outcomes |
| Windred 2024 Sleep 47:zsad253 | VERIFIED | https://pubmed.ncbi.nlm.nih.gov/37738616/ | Regularity vs all-cause mortality, 60,977 UK Biobank adults |
| Mishra 2020 Nat Biomed Eng 4:1208 | CORRECTED | https://doi.org/10.1038/s41551-020-00640-6 | Supports RHR deviation, not HRV fall; "+5 bpm" is not from the paper |
| Radin 2020 Lancet Digit Health 2:e85 | CORRECTED | https://doaj.org/article/0b19ae2d635a4893af58fc85285cdef4 | Population ILI surveillance; page e85 not independently confirmed |
| Waterhouse 2007 Lancet 369:1117 | VERIFIED | https://doi.org/10.1016/s0140-6736(07)60529-7 | Not HRV-specific; wording narrowed |
| Kim 2018 Psychiatry Investig 15:235 | VERIFIED | https://pubmed.ncbi.nlm.nih.gov/29486547/ | Review of 37 studies, not a cohort |
| "Jaramillo/Sanchez-style" late-meal HRV studies | UNSUPPORTED | none | Not a real citation; removed |
| Reimers 2018 | CORRECTED | https://doi.org/10.3390/jcm7120503 | J Clin Med 7:503 (not IJERPH 15:2897); "3-8 bpm" removed |
| Hellsten & Nyberg 2016 | VERIFIED | https://pubmed.ncbi.nlm.nih.gov/26756625/ | Resting-HR content not confirmed |
| Mujika & Padilla 2000 | VERIFIED | none (Sports Med 30:79-87, 30:145-154 confirmed via records) | Both parts confirmed from records |
| Aune 2017 | CORRECTED | https://pubmed.ncbi.nlm.nih.gov/28552551/ | Nutr Metab Cardiovasc Dis 27:504, not Eur J Prev Cardiol |
| Zhang 2016 CMAJ 188:E53 | VERIFIED | https://pubmed.ncbi.nlm.nih.gov/26598376/ | RR 1.09 per 10 bpm |
| Milanovic 2015 | CORRECTED | https://doi.org/10.1007/s40279-015-0365-0 | HIT +1.2 (+/-0.9) vs endurance, not +0.5 |
| Bacon 2013 | CORRECTED | https://pmc.ncbi.nlm.nih.gov/articles/PMC3774727/ | Absolute L/min; no continuous comparison; "+1 mL/kg/min" removed |
| Helgerud 2007 | CORRECTED | https://pubmed.ncbi.nlm.nih.gov/17414804/ | 7.2% in 4x4, 8 weeks; 90-95% HRmax not verified |
| Wisloff 2007 | CORRECTED | https://pubmed.ncbi.nlm.nih.gov/17548726/ | Heart-failure patients; removed as support for healthy adults |
| Seiler & Kjerland 2006 | VERIFIED (record only) | none (record not retrieved) | Not opened; claim not specific |
| Seiler 2010 IJSPP 5:276 | VERIFIED | none (citation confirmed via secondary source) | Pages 276-291 |
| Stoggl & Sperlich 2014 | VERIFIED | https://pubmed.ncbi.nlm.nih.gov/24550842/ | +11.7% polarized, n=48; 4.8% HIT figure not confirmed |
| Rosenblat 2019 | CORRECTED | https://pubmed.ncbi.nlm.nih.gov/29863593/ | 4 trials, ES -0.66 TT favouring polarized; pages 3491-3500 |
| Laursen & Jenkins 2002 | VERIFIED | https://pubmed.ncbi.nlm.nih.gov/11772161/ | Sports Med 32:53-73 |
| Midgley 2006 Sports Med 36:117 | CORRECTED | https://doi.org/10.2165/00007256-200636020-00003 | About optimal intensity for VO2max; "threshold beats VO2max" claim removed |
| Daniels 2013 | UNSUPPORTED | none | No reference given; removed |
| Firstbeat 2014 white paper | UNSUPPORTED | https://www.firstbeat.com/en/science-and-physiology/fitness-level/ | Exact paper not retrievable; cite method page; "typical error +/-5%" removed |
| Molina-Garcia 2022 | CORRECTED | https://doi.org/10.1007/s40279-021-01639-y | Sports Med 52:1577 (not IJSPP); wide individual error |
| Passler 2019 | CORRECTED | https://pmc.ncbi.nlm.nih.gov/articles/PMC6747132/ | IJERPH 16:3037 (not Front Physiol); MAPE 7.3% Garmin 920XT |
| Kaminsky 2015 | VERIFIED | https://doi.org/10.1016/j.mayocp.2015.07.026 | Superseded by 2022 for tables |
| Kaminsky 2022 | VERIFIED | https://doi.org/10.1016/j.mayocp.2021.08.020 | 97(2):285-293; treadmill 1.5-4.6 lower than 2015 |
| Liguori 2021 ACSM Guidelines 11e | VERIFIED (not opened) | none | Textbook; percentile tables not checked |
| Nes 2011 MSSE 43:1849 | CORRECTED | https://pmc.ncbi.nlm.nih.gov/articles/PMC4245230/ | Wrong; HUNT3 norms are Loe 2014 PLoS One |
| Ostchega 2011 NHSR 41 | VERIFIED | https://stacks.cdc.gov/view/cdc/12363 | 47,610 participants |
| Quer 2020 | CORRECTED | https://pmc.ncbi.nlm.nih.gov/articles/PMC7001906 | PLOS ONE 15:e0227709 (not BMJ Open); variability study not norms |
| Nunan 2010 PACE 33:1407 | VERIFIED | https://doi.org/10.1111/j.1540-8159.2010.02841.x | 44 studies, 21,438 participants |
| Shaffer & Ginsberg 2017 | VERIFIED | https://pubmed.ncbi.nlm.nih.gov/29034226/ | |
| Newey-West 1987; Benjamini-Hochberg 1995 | NOT CHECKED | none | Standard statistical references, not searched |

## 9. Backend as built (deviations from section 4)

Additive fields: `baseline.mean_7d`/`n_7d`; `message` (optional, with `state`); `context` (VO2max weight/heat notes, `[{id, numbers, text}]`); `citations` (id -> {id, short, title, authors, year, journal, quality, summary, verified}; `quality` is the study type and `summary` one sentence of what the source supports plus its caveat, both from `docs/improve-sources.json`; `doi`/`url` are present when the verification pass found one; `verified` is false for the few entries it could not check; watch flags can now have an empty `citations` list, e.g. `sleep_debt`, which is Cadence's own rule). Rule/watch wording was audited against the Verification log: thresholds are labelled as Cadence's own rules of thumb, VO2max text carries Garmin's wide individual error, no rule claims HRV-guided training raises VO2max; `drivers[].statement` and `review.statement` (ready-made non-causal text); `progress[].label`; `data.missing_signals` as designed. `start[]` has exactly the designed keys (internal `domain`/`planner_hint` are not exposed).
Behaviour: `focus` is `null` when there is nothing to propose or the state is not `ready`; when `collecting`, `watch` is still computed (needs only 14 nights) but `start`, `drivers`, `focus` are empty. Watch flags are global (not per metric); the summary tags them hrv or resting_hr. `benchmarks` is keyed by metric plus `profile_missing`; NO population tables are bundled (band is `null`, percentile `null`) until they are transcribed from the papers. The watch template ends "This is not medical advice." (the word "diagnos" is on the forbidden list). Driver 95% ranges for HRV/RHR are recovered from the p-value and effective n (approximate). Not built: rules 6 and the low-variability watch prompt; the live weekly plan does not consume an accepted focus yet (`plan.weekly_plan(c, focus_hints=...)` and `focus.apply_hints` exist and are tested). `POST /api/focus` and `/api/focus/{id}/dismiss` are not phone-writable; `focus_plans` table is migration 0030.
Summary `GET /api/improve`: `{as_of, state, focus: {check_on, metric, priority: {title, behaviour, target_metrics}} | null, watch: [{metric, id, severity, title}]}`.
