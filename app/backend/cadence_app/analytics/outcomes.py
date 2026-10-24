"""Is the training actually working? The last 12 weeks against the 12 before, marker by marker.

Descriptive on purpose: it lines up what changed in fitness and efficiency, in the body (resting HR, HRV, sleep), in what you
did (load, hard share, plan adherence) and in what it cost (days of pain, illness, feeling flat). It does not say the plan
caused any of it; a change smaller than the marker's usual noise is reported as "no clear change" and a window with too few
points as missing, never as zero.
"""

from __future__ import annotations

from datetime import date, timedelta
from statistics import median

from cadence_app.analytics import athlete as A

WEEKS = 12
# marker: (label, unit, higher_is_better, smallest change worth reporting)
MARKERS = {
    "fitness": ("Fitness", "", True, 0.03),
    "efficiency": ("Aerobic efficiency", "%", True, 0.015),
    "critical_speed": ("Critical speed", "%", True, 0.01),
    "vo2max": ("VO₂ max", "", True, 1.0),
    "resting_hr": ("Resting heart rate", "bpm", False, 1.0),
    "hrv": ("HRV", "%", True, 0.03),
    "sleep": ("Sleep", "h", True, 0.2),
}
PERFORMANCE = ("fitness", "efficiency", "critical_speed", "vo2max")
MIN_POINTS = {"efficiency": 4, "resting_hr": 14, "hrv": 14, "sleep": 14, "vo2max": 2}


def _med(values: list[float]) -> float | None:
    return float(median(values)) if values else None


def _series_window(series: A.Series, start: date, end: date) -> list[float]:
    return [series[d] for d in A.daterange(start, end) if d in series]


def _marker(key: str, now: float | None, before: float | None, n_now: int, n_before: int, relative: bool) -> dict:
    label, unit, higher, floor = MARKERS[key]
    need = MIN_POINTS.get(key, 1)
    out = {"key": key, "label": label, "unit": unit, "now": now, "before": before, "n": [n_now, n_before], "higher_is_better": higher}
    if now is None or before is None or n_now < need or n_before < need:
        return {**out, "change": None, "state": "missing"}
    change = (now - before) / before if relative and before else now - before
    out["change"] = round(change * 100, 1) if relative else round(change, 1)
    if abs(change) < floor:
        out["state"] = "flat"
    else:
        out["state"] = "better" if (change > 0) == higher else "worse"
    return out


def _window_bounds(end: date, k: int) -> tuple[date, date]:
    return end - timedelta(weeks=WEEKS * (k + 1)) + timedelta(days=1), end - timedelta(weeks=WEEKS * k)


def summarise(c: dict, plans: list[dict] | None = None) -> dict:
    as_of = c["as_of"]
    (s1, e1), (s0, e0) = _window_bounds(as_of, 0), _window_bounds(as_of, 1)
    if s0 < c["first"]:
        return {"enough": False, "reason": f"Needs {2 * WEEKS} weeks of history; you have {max((as_of - c['first']).days // 7, 0)}.", "weeks": WEEKS}
    s = c["series"]
    markers = []
    p_now, p_before = c["pmc_by_day"].get(e1), c["pmc_by_day"].get(e0)
    markers.append(_marker("fitness", p_now["fitness"] if p_now else None, p_before["fitness"] if p_before else None, 1, 1, True))
    ef_now = [p["ef"] for p in c["eff"] if s1 <= p["day"] <= e1]
    ef_before = [p["ef"] for p in c["eff"] if s0 <= p["day"] <= e0]
    markers.append(_marker("efficiency", _med(ef_now), _med(ef_before), len(ef_now), len(ef_before), True))
    hist = (c.get("performance") or {}).get("history") or []
    near = lambda d: min((h for h in hist if abs((h["day"] - d).days) <= 20), key=lambda h: abs((h["day"] - d).days), default=None)  # noqa: E731
    cs_now, cs_before = near(e1), near(e0)
    markers.append(_marker("critical_speed", cs_now["cs_mps"] if cs_now else None, cs_before["cs_mps"] if cs_before else None, int(bool(cs_now)), int(bool(cs_before)), True))
    vo_now, vo_before = _series_window(s.get("vo2max", {}), s1, e1), _series_window(s.get("vo2max", {}), s0, e0)
    markers.append(_marker("vo2max", vo_now[-1] if vo_now else None, vo_before[-1] if vo_before else None, len(vo_now), len(vo_before), False))
    for key, metric, rel in (("resting_hr", "resting_hr", False), ("hrv", "hrv", True), ("sleep", "sleep_hours", False)):
        a, b = _series_window(s.get(metric, {}), s1, e1), _series_window(s.get(metric, {}), s0, e0)
        markers.append(_marker(key, _med(a), _med(b), len(a), len(b), rel))

    def context(start: date, end: date) -> dict:
        acts = [a for a in c["acts"] if start <= a.day <= end and A.is_training(a)]
        weeks = (end - start).days / 7
        endurance = [a for a in acts if a.family in A.INTENSITY_FAMILIES]
        plan_rows = [p for p in (plans or []) if start <= p["day"] <= end and p.get("status") in ("done", "missed")]
        wb = {d: e for d, e in (c.get("wellbeing") or {}).items() if start <= d <= end}
        return {
            "load_per_week": round(sum(a.load for a in acts) / weeks),
            "sessions_per_week": round(len(acts) / weeks, 1),
            "hard_share_pct": round(100 * sum(1 for a in endurance if A.is_hard(a)) / len(endurance)) if len(endurance) >= 6 else None,
            "adherence_pct": round(100 * sum(1 for p in plan_rows if p["status"] == "done") / len(plan_rows)) if len(plan_rows) >= 4 else None,
            "plans": len(plan_rows),
            "checkins": len(wb),
            "pain_days": sum(1 for e in wb.values() if (e.get("pain_level") or 0) >= 1),
            "ill_days": sum(1 for e in wb.values() if (e.get("illness") or 0) >= 1),
            "flat_days": sum(1 for e in wb.values() if e.get("feel") is not None and e["feel"] <= 2),
        }

    now_ctx, before_ctx = context(s1, e1), context(s0, e0)
    perf = [m for m in markers if m["key"] in PERFORMANCE and m["state"] != "missing"]
    better, worse = sum(m["state"] == "better" for m in perf), sum(m["state"] == "worse" for m in perf)
    body = [m for m in markers if m["key"] not in PERFORMANCE and m["state"] != "missing"]
    body_worse = sum(m["state"] == "worse" for m in body)
    if len(perf) < 2:
        verdict = "unclear"
    elif better >= 2 and worse == 0:
        verdict = "improving"
    elif worse >= 2 and better == 0:
        verdict = "slipping"
    elif better == 0 and worse == 0:
        verdict = "holding"
    elif worse == 0:
        verdict = "edging_up"
    elif better == 0:
        verdict = "edging_down"
    else:
        verdict = "mixed"
    cost_up = (now_ctx["pain_days"] + now_ctx["ill_days"]) - (before_ctx["pain_days"] + before_ctx["ill_days"])
    return {"enough": True, "weeks": WEEKS, "windows": {"now": [s1, e1], "before": [s0, e0]}, "markers": markers, "now": now_ctx, "before": before_ctx,
            "verdict": verdict, "better": better, "worse": worse, "body_worse": body_worse, "cost_up": cost_up,
            "checkin_coverage": min(now_ctx["checkins"], before_ctx["checkins"]) >= 14}
