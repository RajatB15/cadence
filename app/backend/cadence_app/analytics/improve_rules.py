"""Improve, part 2: "what to start" rules (pure). Each rule is `(c, d) -> dict | None`.

`c` is the shared insights context, `d` the graded drivers for the requested metric (`{"metric", "drivers"}`).
A rule returns numbers and ids only; wording lives in notes.py and citations are KEYS into improve_sources.py.
Every rule has a minimum-data guard and returns None when its inputs are missing (a missing value is never zero):
sessions without zone data are not counted as easy or hard.
Practical thresholds (70% easy, 25% moderate, 45 min sleep gap, 60 min bedtime SD, 150 easy min/week, 5 building
weeks, 7 idle days, 3 hard days a week) are Cadence's own rule-of-thumb prompts, not taken from any paper and not
tuned to the individual; the text says so where a threshold is shown.
Sources (what each supports, see improve_sources.py): Seiler 2010 (about 80% low-intensity time in elite athletes);
Stoggl & Sperlich 2014 and Rosenblat 2019 (polarised vs threshold: small, preliminary); Helgerud 2007 and Milanovic
2015 (interval training and VO2max in healthy adults; wide spread); Meeusen 2013 (no single marker; heavy load plus
too little recovery); Plews 2014 (nine rowers: HRV tended to be lower with more high-intensity training); Windred 2024
and Phillips 2017 (sleep regularity; cohort and sleep-index study); Pietila 2018 and Spaak 2010 (alcohol and overnight
autonomic measures); Mujika & Padilla 2000 (detraining); Reimers 2018 (endurance training and resting HR).
No rule claims that HRV-guided training improves VO2max (Kiviniemi 2007, Vesterinen 2016 and a 2021 meta-analysis
found no clear advantage) and Garmin's VO2max is only ever called an estimate.
Score = impact x confidence x ease (1-3 each); confidence comes from the sample size, not from the size of the gap.
"""

from __future__ import annotations

from datetime import date, timedelta
from statistics import fmean

from cadence_app.analytics import athlete as A
from cadence_app.analytics import drivers as D
from cadence_app.analytics import timeoff as T

DAY = timedelta(days=1)
MIN_SESSIONS, MIN_MINUTES = 6, 180
EASY_MIN_PCT, MODERATE_MAX_PCT = 70, 25
HARD_MAX_SHARE = 25
SLEEP_GAP_H, BEDTIME_SD_MIN, SRI_LOW, SLEEP_MIN_NIGHTS = 0.75, 60, 70, 10
GAP_DAYS, BUILD_WEEKS, EASY_MIN_PER_WEEK = 7, 5, 150
ALCOHOL_MIN_EXPOSED = 8


def confidence(n: float, low: int, high: int) -> int:
    """1 = at the minimum, 3 = well beyond it (n in sessions, nights or days as the rule defines)."""
    return 1 if n < low * 2 else 2 if n < high else 3


def _rec(rid: str, domain: str, tags: list[str], numbers: dict, cites: list[str], timescale: str, impact: int, conf: int, ease: int, hint: dict | None = None) -> dict:
    return {"id": rid, "domain": domain, "tags": tags, "numbers": numbers, "citations": cites, "timescale": timescale, "impact": impact,
            "confidence": conf, "ease": ease, "score": impact * conf * ease, "planner_hint": hint or {}}


def _zone_acts(c: dict, days: int) -> list[A.Act]:
    since = c["as_of"] - (days - 1) * DAY
    return [a for a in c["acts"] if since <= a.day <= c["as_of"] and a.family in A.INTENSITY_FAMILIES and len(a.zones_s) >= 5]


def covered_by_time_off(c: dict, start: date, end: date) -> bool:
    """Whether any day of the window is inside logged time off (such windows never count as a miss)."""
    cfg, periods, today = c.get("plan_settings") or T.DEFAULTS, c.get("time_off") or [], c.get("today", c["as_of"])
    return any(T.day_factors(periods, cfg, today, d)[0] < 1.0 for d in A.daterange(start, end))


def easy_share_low(c: dict, d: dict) -> dict | None:
    s = c.get("split_28")
    if not s or (s["sessions"] or 0) < MIN_SESSIONS or s["minutes"] < MIN_MINUTES:
        return None
    if s["easy_pct"] >= EASY_MIN_PCT and s["moderate_pct"] <= MODERATE_MAX_PCT:
        return None
    n = {"easy_pct": s["easy_pct"], "moderate_pct": s["moderate_pct"], "target_pct": 80, "minutes": s["minutes"], "sessions": s["sessions"], "window_days": 28}
    return _rec("easy_share_low", "intensity", ["hrv", "resting_hr", "vo2max"], n, ["seiler2010", "stoggl2014", "rosenblat2019"], "4-8 weeks", 3,
                confidence(s["sessions"], MIN_SESSIONS, 20), 2, {"intensity_bias": "easier"})


def too_few_hard(c: dict, d: dict) -> dict | None:
    acts = _zone_acts(c, 28)
    if len(acts) < 12:  # at least 3 sessions a week with zone data
        return None
    hard = sum(A.is_hard(a) for a in acts)
    if hard >= 4:
        return None
    trend = c.get("eff_trend")
    if trend and trend.get("significant") and (trend.get("change_pct_90d") or 0) > 0:
        return None  # efficiency is already improving: nothing to add
    n = {"hard_sessions": hard, "sessions": len(acts), "per_week": round(hard / 4, 1), "window_days": 28}
    return _rec("too_few_hard", "intensity", ["vo2max"], n, ["helgerud2007", "milanovic2015", "molinagarcia2022"], "6-12 weeks", 3, confidence(len(acts), 12, 24), 2, {"add_key_session": "vo2"})


def too_many_hard(c: dict, d: dict) -> dict | None:
    acts = _zone_acts(c, 28)
    base = D.baseline(c["series"].get("hrv", {}), c["as_of"], "hrv")
    if len(acts) < MIN_SESSIONS or base is None or base["mean_7d"] is None:
        return None  # needs HRV: without it a hard week is only a hard week
    hard_days = {a.day for a in acts if A.is_hard(a) and a.day > c["as_of"] - 7 * DAY}
    share = round(sum(A.is_hard(a) for a in acts) / len(acts) * 100)
    if not (share > HARD_MAX_SHARE or len(hard_days) >= 3) or base["mean_7d"] >= base["band"][0]:
        return None
    n = {"hard_share_pct": share, "hard_days_7d": len(hard_days), "sessions": len(acts), "hrv_7d": base["mean_7d"], "hrv_band_low": base["band"][0],
         "window_days": 28}
    return _rec("too_many_hard", "recovery", ["hrv", "resting_hr"], n, ["meeusen2013", "plews2014"], "1-2 weeks", 3, confidence(len(acts), MIN_SESSIONS, 16), 2,
                {"intensity_bias": "easier"})


def sleep_pattern_rule(c: dict, d: dict) -> dict | None:
    sp, sri = c.get("sleep_14"), c.get("sleep_regularity")
    if not sp or sp["nights"] < SLEEP_MIN_NIGHTS:
        return None
    short = sp["avg_hours"] < sp["need_hours"] - SLEEP_GAP_H
    erratic = (sp["bedtime_sd_min"] is not None and sp["bedtime_sd_min"] > BEDTIME_SD_MIN) or bool(sri and sri["pairs"] >= 14 and sri["sri"] < SRI_LOW)
    if not (short or erratic):
        return None
    n = {"avg_hours": sp["avg_hours"], "need_hours": sp["need_hours"], "nights": sp["nights"], "bedtime_sd_min": sp["bedtime_sd_min"],
         "sri": sri["sri"] if sri else None, "short": short, "erratic": erratic, "window_days": 14}
    return _rec("sleep_pattern", "sleep", ["hrv", "resting_hr"], n, ["windred2024", "phillips2017"], "2-4 weeks", 2, confidence(sp["nights"], SLEEP_MIN_NIGHTS, 14), 2)


def alcohol_nights(c: dict, d: dict) -> dict | None:
    row = next((r for r in d["drivers"] if r.get("_behaviour") == "alcohol" and r["grade"] == "clear"), None)
    if not row or row["n_exposed"] < ALCOHOL_MIN_EXPOSED:
        return None
    worse = row["diff"] < 0 if row["_higher_is_better"] else row["diff"] > 0
    if not worse:
        return None
    logged = len([x for x, v in (c["journal"]["answers"].get("alcohol") or {}).items() if x > c["as_of"] - 28 * DAY and v is not None])
    n = {"diff": row["diff"], "unit": row["unit"], "ci": row["ci"], "n_exposed": row["n_exposed"], "n_reference": row["n_reference"], "logged_days_28": logged,
         "outcome": row["_outcome"], "window_days": 28}
    return _rec("alcohol_nights", "alcohol", [d["metric"]], n, ["pietila2018", "spaak2010"], "2-4 weeks", 2, confidence(row["n_exposed"], ALCOHOL_MIN_EXPOSED, 20), 2)


def habit_driver(c: dict, d: dict) -> dict | None:
    """Rule 10: any other journal behaviour (late meal, screens, travel...) whose clear association is unfavourable."""
    for row in d["drivers"]:
        b = row.get("_behaviour")
        if not b or b == "alcohol" or row["grade"] != "clear" or min(row["n_exposed"], row["n_reference"]) < 8:
            continue
        if (row["diff"] < 0) != row["_higher_is_better"]:
            continue
        n = {"cause": row["_cause"], "exposure": row["exposure"], "reference": row["reference"], "diff": row["diff"], "unit": row["unit"], "ci": row["ci"],
             "n_exposed": row["n_exposed"], "n_reference": row["n_reference"], "outcome": row["_outcome"], "window_days": 90}
        return _rec(f"habit_{b}", "habit", [d["metric"]], n, [], "2-4 weeks", 1, confidence(row["n_exposed"], 8, 20), 2)
    return None


def _complete_weeks(c: dict) -> list[dict]:
    return [w for w in c["weeks"] if w["complete"]]


def volume_fallen(c: dict, d: dict) -> dict | None:
    ws = _complete_weeks(c)
    if len(ws) < 8:
        return None
    last, prev = ws[-4:], ws[-8:-4]
    now, before = fmean(w["hours"] for w in last) * 60, fmean(w["hours"] for w in prev) * 60
    if before < 60 or now > before * 0.8 or covered_by_time_off(c, last[0]["week"], c["as_of"]):
        return None
    n = {"minutes_per_week": round(now), "previous_minutes_per_week": round(before), "change_pct": round((now / before - 1) * 100), "weeks": 4, "window_days": 28}
    return _rec("volume_fallen", "volume", ["vo2max", "resting_hr"], n, ["mujika2000"], "4-8 weeks", 2, 1, 2, {"volume_bias": "up"})


def no_deload(c: dict, d: dict) -> dict | None:
    ws = _complete_weeks(c)
    if len(ws) < 7:
        return None
    run = 0
    for i in range(len(ws) - 1, 2, -1):
        w = ws[i]
        ref = max(x["load"] for x in ws[i - 3:i])
        if w["load"] <= 0 or w["load"] <= 0.8 * ref or covered_by_time_off(c, w["week"], w["week"] + 6 * DAY):
            break
        run += 1
    if run < BUILD_WEEKS:
        return None
    return _rec("no_deload", "recovery", ["hrv", "resting_hr", "vo2max"], {"weeks_without_easier_week": run, "window_days": run * 7}, ["meeusen2013"], "1 week", 2, 2, 3,
                {"deload_week": True})


def long_gap(c: dict, d: dict) -> dict | None:
    done = [a.day for a in c["acts"] if A.is_training(a) and a.day <= c["as_of"]]
    if not done or max(done) < c["as_of"] - 90 * DAY:
        return None
    gap = (c["as_of"] - max(done)).days
    if gap < GAP_DAYS or covered_by_time_off(c, max(done) + DAY, c["as_of"]):
        return None
    return _rec("long_gap", "volume", ["hrv", "resting_hr", "vo2max"], {"days_without_training": gap, "window_days": gap}, ["mujika2000"],
                "2-4 weeks", 2, 2, 3, {"volume_bias": "hold"})


def no_aerobic_base(c: dict, d: dict) -> dict | None:
    since = c["as_of"] - 27 * DAY
    endu = [a for a in c["acts"] if since <= a.day <= c["as_of"] and a.family in A.INTENSITY_FAMILIES]
    zoned = [a for a in endu if len(a.zones_s) >= 5]
    if len(endu) < MIN_SESSIONS or len(zoned) < 0.8 * len(endu) or covered_by_time_off(c, since, c["as_of"]):
        return None
    easy = sum(sum(a.zones_s[:3]) for a in zoned) / 60 / 4
    if easy >= EASY_MIN_PER_WEEK:
        return None
    return _rec("no_aerobic_base", "volume", ["resting_hr"], {"easy_minutes_per_week": round(easy), "sessions": len(zoned), "window_days": 28}, ["reimers2018"], "8-24 weeks",
                2, confidence(len(zoned), MIN_SESSIONS, 16), 2, {"volume_bias": "up"})


RULES = (easy_share_low, too_few_hard, too_many_hard, sleep_pattern_rule, alcohol_nights, habit_driver, volume_fallen, no_deload, long_gap, no_aerobic_base)


def run(c: dict, d: dict) -> list[dict]:
    """All rules that fire for the metric, best score first (ties by id so the order is deterministic)."""
    out = [r for rule in RULES if (r := rule(c, d)) and d["metric"] in r["tags"]]
    out.sort(key=lambda r: (-r["score"], r["id"]))
    return out


def context_notes(c: dict, metric: str) -> list[dict]:
    """Rule 11: VO2max context only (not advice): weight change and hot runs both move Garmin's estimate."""
    if metric != "vo2max":
        return []
    out = []
    w = [(day, kg) for day, kg in c.get("weights") or [] if day >= c["as_of"] - 56 * DAY]
    if len(w) >= 3 and w[0][1] > 0:
        pct = (w[-1][1] / w[0][1] - 1) * 100
        if abs(pct) > 3:
            out.append({"id": "vo2_weight", "numbers": {"change_pct": round(pct, 1), "weigh_ins": len(w), "window_days": 56}})
    runs = [x for x in (c.get("weather_runs") or {}).values()]
    recent = [a for a in c["acts"] if a.family == "run" and a.day > c["as_of"] - 56 * DAY and a.id in (c.get("weather_runs") or {})]
    hot = [a for a in recent if c["weather_runs"][a.id].get("hot")]
    if runs and len(recent) >= 4 and len(hot) >= len(recent) / 2:
        out.append({"id": "vo2_heat", "numbers": {"hot_runs": len(hot), "runs": len(recent), "window_days": 56}})
    return out
