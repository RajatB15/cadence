"""What you tell Cadence about how you feel, and what that changes.

The watch measures HRV, resting heart rate and sleep, but it cannot feel a sore knee, a heavy week at work or the start of a
cold. Self-reported state is the most direct early warning of overreaching and illness in the monitoring literature
(Saw, Main & Gastin 2016: subjective measures respond to training load more consistently than objective ones), so a daily
check-in is allowed to override the plan. It only ever pulls towards less: a good day never adds training.

Pure logic on plain data. Entries are {"feel" 1-5, "soreness" 0-3, "pain_level" 0-3, "pain_area", "illness" 0-2, "life_stress" 1-3};
the wording is in notes.py.
"""

from __future__ import annotations

from collections import Counter
from datetime import date, timedelta

from cadence_app.analytics import athlete as A

LEVELS = {"rest": 3, "easy": 2, "watch": 1}
DAY = timedelta(days=1)
DISAGREE_MIN_DAYS = 7
DISAGREE_FLAG = 3
HEAVY_STRESS_DAYS = 4


def state(entry: dict | None) -> dict | None:
    """How today's check-in should change today: level (rest | easy | watch) and the reasons, strongest first."""
    if not entry:
        return None
    reasons: list[tuple[str, str]] = []  # (level, code)
    if entry.get("illness") == 2:
        reasons.append(("rest", "ill"))
    if entry.get("pain_level") == 3:
        reasons.append(("rest", "pain_stops"))
    if entry.get("pain_level") == 2:
        reasons.append(("easy", "pain_hurts"))
    if entry.get("illness") == 1:
        reasons.append(("easy", "run_down"))
    if entry.get("soreness") == 3:
        reasons.append(("easy", "very_sore"))
    if entry.get("feel") is not None and entry["feel"] <= 2:
        reasons.append(("easy", "feel_low"))
    if entry.get("pain_level") == 1:
        reasons.append(("watch", "niggle"))
    if entry.get("life_stress") == 3:
        reasons.append(("watch", "heavy_stress"))
    if not reasons:
        return {"level": None, "codes": [], "area": entry.get("pain_area")}
    reasons.sort(key=lambda r: -LEVELS[r[0]])
    return {"level": reasons[0][0], "codes": [c for _, c in reasons], "area": entry.get("pain_area")}


def disagrees(entry: dict | None, readiness: float | None) -> str | None:
    """'flat' when you feel poor but the watch is happy, 'fresh' when it is the other way round."""
    if not entry or entry.get("feel") is None or readiness is None:
        return None
    if entry["feel"] <= 2 and readiness >= 70:
        return "flat"
    if entry["feel"] >= 4 and readiness < 50:
        return "fresh"
    return None


def hold(entries: dict[date, dict], today: date) -> str | None:
    """A short reason to hold the week back (the plan's absorb phase), from the last two days and the last four."""
    recent = [entries[d] for d in (today - DAY, today) if d in entries]
    if any(e.get("illness") == 2 for e in recent):
        return "illness you reported"
    if any((e.get("pain_level") or 0) >= 2 for e in recent):
        return "pain you reported"
    if len(recent) == 2 and all(e.get("illness") == 1 for e in recent):
        return "feeling run down two days running"
    last4 = [entries[d]["feel"] for d in (today - i * DAY for i in range(4)) if d in entries and entries[d].get("feel") is not None]
    if len(last4) >= 3 and sum(1 for f in last4 if f <= 2) >= 3:
        return "feeling flat for several days"
    return None


def stress_high(entries: dict[date, dict], today: date) -> bool:
    return sum(1 for i in range(7) if entries.get(today - i * DAY, {}).get("life_stress") == 3) >= HEAVY_STRESS_DAYS


def patterns(entries: dict[date, dict], readiness: dict[date, float], acts: list[A.Act], today: date) -> dict:
    """The recurring things worth saying out loud, as plain data."""
    out: dict = {}
    window = [d for d in (today - i * DAY for i in range(21)) if d in entries]
    areas = Counter(entries[d]["pain_area"] for d in window if entries[d].get("pain_area") and (entries[d].get("pain_level") or 0) >= 1)
    if areas:
        area, days = areas.most_common(1)[0]
        if days >= 3:
            out["recurring_pain"] = {"area": area, "days": days, "worst": max(entries[d].get("pain_level") or 0 for d in window if entries[d].get("pain_area") == area)}
    pairs = [(d, entries[d], readiness[d]) for d in (today - i * DAY for i in range(14)) if d in entries and d in readiness and entries[d].get("feel") is not None]
    if len(pairs) >= DISAGREE_MIN_DAYS:
        kinds = [k for _, e, r in pairs if (k := disagrees(e, r))]
        if len(kinds) >= DISAGREE_FLAG:
            flat = kinds.count("flat")
            out["disagreement"] = {"days": len(kinds), "of": len(pairs), "mostly": "flat" if flat * 2 >= len(kinds) else "fresh"}
    trained = {a.day for a in acts if A.is_training(a)}
    hard = {a.day for a in acts if A.is_hard(a)}
    since = today - 20 * DAY
    through_pain = sorted(d for d, e in entries.items() if since <= d <= today and (e.get("pain_level") or 0) >= 2 and d in trained)
    if through_pain:
        out["through_pain"] = {"days": len(through_pain), "hard": sum(1 for d in through_pain if d in hard)}
    through_ill = sorted(d for d, e in entries.items() if since <= d <= today and e.get("illness") == 2 and d in trained)
    if through_ill:
        out["through_illness"] = {"days": len(through_ill)}
    if stress_high(entries, today):
        out["heavy_stress"] = {"days": sum(1 for i in range(7) if entries.get(today - i * DAY, {}).get("life_stress") == 3)}
    recent = [entries[d]["feel"] for d in (today - i * DAY for i in range(7)) if d in entries and entries[d].get("feel") is not None]
    before = [entries[d]["feel"] for d in (today - i * DAY for i in range(7, 28)) if d in entries and entries[d].get("feel") is not None]
    if len(recent) >= 4 and len(before) >= 6:
        drop = sum(before) / len(before) - sum(recent) / len(recent)
        if drop >= 1.0:
            out["feel_drop"] = {"now": round(sum(recent) / len(recent), 1), "before": round(sum(before) / len(before), 1), "n": len(recent)}
    return out


def recovery_wins(c: dict, days: int = 14) -> dict:
    """Recovery behaviours in the last `days`: easy days kept easy, rest after a hard day, nights at your sleep need, and times you listened."""
    as_of = c["as_of"]
    start = as_of - (days - 1) * DAY
    acts = [a for a in c["acts"] if start <= a.day <= as_of and a.family in A.INTENSITY_FAMILIES]
    kinds = [(a, A.intensity(a)) for a in acts]
    easy_kept = sum(1 for _, k in kinds if k and k["kind"] == "easy")
    grey = sum(1 for _, k in kinds if k and k["kind"] == "grey")
    hard_days = {a.day for a in c["acts"] if A.is_hard(a)}
    trained_days = {a.day for a in c["acts"] if A.is_training(a)}
    after_hard = [d for d in hard_days if start <= d < as_of]
    eased_after_hard = sum(1 for d in after_hard if (d + DAY) not in hard_days)
    need = (c.get("sleep_need") or {}).get("hours", 8.0)
    sleep = c["series"].get("sleep_hours", {})
    nights = [sleep[d] for d in (as_of - i * DAY for i in range(days)) if d in sleep]
    wb = c.get("wellbeing") or {}
    listened = sum(1 for d, e in wb.items() if start <= d <= as_of and (state(e) or {}).get("level") in ("rest", "easy") and d not in hard_days)
    return {"days": days, "easy_kept": easy_kept, "grey": grey, "sessions": len(acts), "eased_after_hard": eased_after_hard, "hard_days": len(after_hard),
            "nights": len(nights), "nights_at_need": sum(1 for h in nights if h >= need), "need": need, "listened": listened,
            "rest_days": sum(1 for i in range(days) if (start + i * DAY) not in trained_days)}
