"""Cadence Score: one daily number for how well you train, recover, sleep and move, with the gaps behind it.

Every factor maps a personal metric onto 0-100 against a published target (or your own baseline) and is computable
for any past day, so the score has an honest history. Missing data drops a factor; it never counts as zero.
Planned recovery and taper weeks are not penalised for lower load or a dip in fitness: that dip is the point.
"""

from __future__ import annotations

from datetime import date, timedelta
from statistics import fmean, median, pstdev

from cadence_app.analytics import athlete as A
from cadence_app.analytics import notes
from cadence_app.analytics import plan as training_plan
from cadence_app.analytics import recovery as R

GROUPS = {
    "train": ("Train", 0.30, "How well your training is structured to make you fitter"),
    "recover": ("Recover", 0.30, "How well your body is absorbing the work"),
    "sleep": ("Sleep", 0.25, "How much, how well and how regularly you sleep"),
    "move": ("Move", 0.15, "Everyday activity outside of workouts"),
}
DAY = timedelta(days=1)


def _window(series: A.Series, start: date, end: date) -> list[float]:
    return [series[d] for d in A.daterange(start, end) if d in series]


def _f(key: str, group: str, label: str, score: float | None, value: str, target: str, tip: str, weight: float = 1.0) -> dict | None:
    if score is None:
        return None
    return {"key": key, "group": group, "label": label, "score": round(A.clamp(score)), "value": value, "target": target,
            "tip": tip, "weight": weight}


def factors(c: dict, d: date, hard: set[date] | None = None) -> list[dict]:  # noqa: C901 - one block per factor
    s = c["series"]
    week = (d - 6 * DAY, d)
    out: list[dict | None] = []

    # ---- recover
    hrv7 = _window(s.get("hrv", {}), *week)
    lo, hi = s.get("hrv_balanced_low", {}).get(d), s.get("hrv_balanced_high", {}).get(d)
    if len(hrv7) >= 3:
        v = fmean(hrv7)
        if lo and hi and hi > lo:
            sc = 75 + 20 * (v - lo) / (hi - lo) if lo <= v <= hi else 85 if v > hi else 75 - (lo - v) / (0.1 * lo) * 25
            target = f"{lo:.0f}–{hi:.0f} ms (your balanced range)"
        else:
            base = _window(s.get("hrv", {}), d - 67 * DAY, d - 7 * DAY)
            sc = 80 + 25 * (v - fmean(base)) / (pstdev(base) or 1) if len(base) >= A.MIN_BASELINE else None
            target = f"≥ {fmean(base):.0f} ms (your baseline)" if base else ""
        out.append(_f("hrv", "recover", "HRV", sc, f"{v:.0f} ms 7-day avg", target,
                      "HRV rises with sleep, easy aerobic volume and lower life stress; it drops with stacked hard days and alcohol."))

    rhr7 = _window(s.get("resting_hr", {}), *week)
    rhr_base = _window(s.get("resting_hr", {}), d - 67 * DAY, d - 7 * DAY)
    if len(rhr7) >= 3 and len(rhr_base) >= A.MIN_BASELINE:
        delta = fmean(rhr7) - fmean(rhr_base)
        out.append(_f("rhr", "recover", "Resting HR", 85 - 8 * delta if delta > 0 else 85 + 4 * -delta,
                      f"{fmean(rhr7):.0f} bpm ({delta:+.1f})", f"≤ {fmean(rhr_base):.0f} bpm (your baseline)",
                      "An elevated resting HR means incomplete recovery, illness or heat; easy days and sleep bring it down."))

    bb = _window(s.get("body_battery", {}), *week)
    if len(bb) >= 3:
        out.append(_f("battery", "recover", "Body Battery", fmean(bb), f"{fmean(bb):.0f} avg morning peak", "≥ 90",
                      "Charges overnight from sleep and drains with stress and training; an earlier night is the fastest fix."))

    stress = _window(s.get("stress", {}), *week)
    if len(stress) >= 3:
        out.append(_f("stress", "recover", "Daytime stress", 130 - 2 * fmean(stress), f"{fmean(stress):.0f} avg", "≤ 25 (rest range)",
                      "Short breathing breaks and walks lower all-day stress; high-stress days cost you sleep quality."))

    # ---- sleep
    hours = _window(s.get("sleep_hours", {}), *week)
    need = notes.need(c)
    if len(hours) >= 3:
        avg = fmean(hours)
        out.append(_f("sleep_duration", "sleep", "Sleep duration", 100 - max(0, need - avg) * 25, f"{avg:.1f} h avg", f"≥ {need:g} h"
                      + (" (your plateau)" if (c.get("sleep_need") or {}).get("personal") else ""),
                      "Each extra 30 minutes in bed is the cheapest performance gain available.", 1.5))
    scores = _window(s.get("sleep_score", {}), *week)
    if len(scores) >= 3:
        out.append(_f("sleep_quality", "sleep", "Sleep quality", fmean(scores), f"{fmean(scores):.0f} avg score", "≥ 85",
                      "Late meals, alcohol, late hard sessions and screens before bed are the usual quality killers."))
    sri = R.sleep_regularity(s.get("bedtime", {}), s.get("wake_time", {}), d - 13 * DAY, d)
    beds = _window(s.get("bedtime", {}), d - 13 * DAY, d)
    if sri:
        # Sleep Regularity Index: regular sleepers score 80+; each point below 85 costs 2.5.
        out.append(_f("sleep_regularity", "sleep", "Sleep regularity", 100 - max(0, 85 - sri["sri"]) * 2.5, f"SRI {sri['sri']}",
                      "SRI ≥ 85", "Same wake time every day, then a lights-out window within 30 minutes; weekends included."))
    elif len(beds) >= 7:
        sd = pstdev(beds)
        out.append(_f("sleep_regularity", "sleep", "Sleep regularity", 100 - max(0, sd - 30) * 1.4, f"±{sd:.0f} min bedtime",
                      "±30 min", "A fixed lights-out window anchors your body clock; your sleep scores drop sharply after 00:30."))

    # ---- train
    p = c["pmc_by_day"].get(d)
    recovering = training_plan.is_recovery_week(c, d)
    if p and p["acwr"]:
        r = p["acwr"]
        lo, hi = (0.5, 1.1) if recovering else (0.8, 1.3)
        sc = 100 if lo <= r <= hi else 100 - (lo - r) * 200 if r < lo else 100 - (r - hi) * 200
        # Half weight: acute:chronic is a weak injury predictor on its own (Impellizzeri 2020).
        out.append(_f("load_balance", "train", "Load balance", sc, f"{r:.2f} acute:chronic", f"{lo}–{hi}" + (" (recovery week)" if recovering else ""),
                      "Grow weekly load gradually (~10%); spikes above 1.5 are where injuries cluster.", 0.5))

    acts = [a for a in c["acts"] if a.day <= d]
    split = A.intensity_split(acts, d - 27 * DAY)
    if split:
        out.append(_f("intensity", "train", "Intensity balance", 100 - 2 * max(0, 80 - split["easy_pct"]),
                      f"{split['easy_pct']}% easy", "~80% easy (Z1–2)",
                      "Run most sessions slow enough to talk; keep intensity for 1–2 dedicated sessions a week.", 1.5))

    hard = hard if hard is not None else notes.hard_days(c)
    recent_hard = sorted(x for x in hard if d - 27 * DAY <= x <= d)
    if recent_hard:
        stacked = sum(1 for x in recent_hard if notes.recent_hard(hard, x) >= 2)
        out.append(_f("spacing", "train", "Hard-day spacing", 100 * (1 - stacked / len(recent_hard)),
                      f"{stacked} of {len(recent_hard)} hard days stacked", "≤ 2 hard days per 7",
                      "Put at least one easy or rest day between hard sessions so each one is high quality."))

    weeks = [w for w in A.weekly(acts, c["load"], d - timedelta(weeks=12), d) if w["complete"]][-12:]
    if len(weeks) >= 4:
        good = sum(1 for w in weeks if w["total_sessions"] >= 3)
        out.append(_f("consistency", "train", "Consistency", good / len(weeks) * 100, f"{good}/{len(weeks)} weeks with 3+ sessions",
                      "Every week", "Protect a minimum of three sessions in busy weeks; consistency beats heroics."))

    # In a recovery week, judge the trend up to the week's start: the planned dip isn't a lost gain.
    ref = A.week_start(d) - DAY if recovering else d
    p_ref, p_then = c["pmc_by_day"].get(ref), c["pmc_by_day"].get(ref - 28 * DAY)
    if p_ref and p_then and p_then["fitness"] > 5:
        change = (p_ref["fitness"] - p_then["fitness"]) / p_then["fitness"] * 100
        out.append(_f("fitness_trend", "train", "Fitness trend", 70 + 3 * change, f"{change:+.0f}% in 4 weeks" + (" before this recovery week" if recovering else ""),
                      "Rising steadily", "Fitness (42-day load) grows when weekly load creeps up without spikes."))

    month = [a for a in acts if d - 27 * DAY <= a.day]
    if any(a.family == "run" for a in month):
        n = sum(1 for a in month if a.family == "strength")
        out.append(_f("strength", "train", "Strength", n / 8 * 100, f"{n} sessions in 4 weeks", "2 a week",
                      "Heavy lower-body and calf/hip work improves running economy and lowers injury risk.", 0.5))

    eff_now = [e["ef"] for e in c["eff"] if d - 45 * DAY < e["day"] <= d]
    eff_then = [e["ef"] for e in c["eff"] if d - 135 * DAY < e["day"] <= d - 45 * DAY]
    if len(eff_now) >= 3 and len(eff_then) >= 3:
        change = (median(eff_now) - median(eff_then)) / median(eff_then) * 100
        out.append(_f("efficiency", "train", "Aerobic efficiency", 70 + 10 * change, f"{change:+.1f}% speed per heartbeat",
                      "Improving", "More easy aerobic volume is the most reliable way to run faster at the same heart rate."))

    # ---- move
    steps = _window(s.get("steps", {}), *week)
    if len(steps) >= 3:
        out.append(_f("steps", "move", "Daily steps", fmean(steps) / 100, f"{fmean(steps):,.0f} avg", "≥ 10,000",
                      "Easy walking between sessions aids recovery and adds low-cost aerobic volume."))
    im = s.get("intensity_minutes", {})
    if any(x in im for x in A.daterange(*week)):
        total = sum(im.get(x, 0) for x in A.daterange(*week))
        out.append(_f("intensity_minutes", "move", "Intensity minutes", total / 150 * 100, f"{total:.0f} min / 7 days", "≥ 150",
                      "Moderate or vigorous activity across the week; workouts and brisk walks both count."))

    return [f for f in out if f is not None]


def label(score: float) -> str:
    return "Elite habits" if score >= 85 else "On track" if score >= 70 else "Building" if score >= 55 else "Off track"


def daily(c: dict, d: date, hard: set[date] | None = None) -> dict | None:
    fs = factors(c, d, hard)
    if not fs:
        return None
    groups = {}
    for key, (name, weight, blurb) in GROUPS.items():
        members = [f for f in fs if f["group"] == key]
        if members:
            w = sum(f["weight"] for f in members)
            groups[key] = {"key": key, "label": name, "blurb": blurb, "weight": weight,
                           "score": round(sum(f["score"] * f["weight"] for f in members) / w)}
    total_w = sum(g["weight"] for g in groups.values())
    overall = sum(g["score"] * g["weight"] for g in groups.values()) / total_w
    for f in fs:
        g = groups[f["group"]]
        member_w = sum(x["weight"] for x in fs if x["group"] == f["group"])
        f["points_lost"] = round(g["weight"] / total_w * f["weight"] / member_w * (100 - f["score"]), 1)
    return {"day": d, "score": round(overall), "label": label(overall), "groups": list(groups.values()), "factors": fs,
            "gaps": sorted((f for f in fs if f["points_lost"] >= 0.5), key=lambda f: -f["points_lost"])}


def report(c: dict, days: int = 90) -> dict | None:
    as_of = c["as_of"]
    hard = notes.hard_days(c)
    today = daily(c, as_of, hard)
    if today is None:
        return None
    history = []
    for d in A.daterange(as_of - timedelta(days=days - 1), as_of):
        if (r := daily(c, d, hard)) is not None:
            history.append({"day": d, "score": r["score"], **{g["key"]: g["score"] for g in r["groups"]}})
    week_ago = next((h["score"] for h in history if h["day"] == as_of - 7 * DAY), None)
    return {**today, "delta_7d": today["score"] - week_ago if week_ago is not None else None, "history": history}


def summary(c: dict) -> dict | None:
    """Compact version for the home page."""
    r = report(c, days=30)
    if r is None:
        return None
    return {"score": r["score"], "label": r["label"], "delta_7d": r["delta_7d"],
            "groups": [{"key": g["key"], "label": g["label"], "score": g["score"]} for g in r["groups"]],
            "top_gaps": [{"label": f["label"], "points_lost": f["points_lost"], "value": f["value"], "target": f["target"]} for f in r["gaps"][:3]],
            "spark": [h["score"] for h in r["history"]]}
