"""Heat context: your personal heat cost on runs, heat-adjusted efficiency, and what tomorrow's weather will do.

- Heat measure: dew point above 10 °C. Dew point captures how hard sweat can cool you and is the most used single
  heat-stress predictor for runners; below ~10 °C it barely matters.
- Personal cost: Theil–Sen slope of run efficiency (vs your median of the previous 60 days) on that measure, trusted
  only with 20+ runs, 5+ of them warm, and a confidence interval entirely below zero.
- Without a personal cost: the widely used temperature + dew point (°F) slowdown table (Hadley).
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from statistics import median

import numpy as np
from scipy import stats

HEAT_FLOOR_C = 10.0
HOT_DEW_C = 18.0
HOT_TEMP_C = 27.0
# (temperature °F + dew point °F) → expected slowdown %, interpolated (Hadley's runners' heat table).
HADLEY = ((100, 0.0), (110, 0.5), (120, 1.5), (130, 2.5), (140, 3.75), (150, 5.25), (160, 7.0), (170, 9.0), (180, 11.0))


def heat(dew_point: float | None) -> float:
    return max(0.0, (dew_point or 0.0) - HEAT_FLOOR_C)


def hot(w: dict) -> bool:
    return (w.get("dew_point") or -99) >= HOT_DEW_C or (w.get("temperature") or -99) >= HOT_TEMP_C


def hadley_pct(temp_c: float | None, dew_c: float | None) -> float:
    if temp_c is None or dew_c is None:
        return 0.0
    total = (temp_c * 9 / 5 + 32) + (dew_c * 9 / 5 + 32)
    if total <= HADLEY[0][0]:
        return 0.0
    for (x0, y0), (x1, y1) in zip(HADLEY, HADLEY[1:]):
        if total <= x1:
            return round(y0 + (y1 - y0) * (total - x0) / (x1 - x0), 1)
    return HADLEY[-1][1]


def model(eff: list[dict], weather: dict[int, dict]) -> dict | None:
    """Efficiency change (%) per °C of dew point above 10 °C, from your own runs."""
    rows = []
    for p in eff:
        w = weather.get(p["id"])
        if not w or w.get("dew_point") is None:
            continue
        prior = [q["ef"] for q in eff if p["day"] - timedelta(days=60) <= q["day"] < p["day"]]
        if len(prior) >= 5:
            rows.append((heat(w["dew_point"]), (p["ef"] / median(prior) - 1) * 100))
    warm = sum(1 for h, _ in rows if h > 3)
    if len(rows) < 20 or warm < 5:
        return {"n": len(rows), "warm": warm, "significant": False, "slope_pct_per_c": None}
    x = np.array([r[0] for r in rows])
    y = np.array([r[1] for r in rows])
    slope, _, lo, hi = stats.theilslopes(y, x)
    return {"n": len(rows), "warm": warm, "slope_pct_per_c": round(float(slope), 2), "ci": [round(float(lo), 2), round(float(hi), 2)],
            "significant": bool(hi < 0)}


def cost_pct(m: dict | None, w: dict) -> tuple[float, str]:
    """Expected efficiency/pace cost (%) in these conditions: personal when established, else Hadley's table."""
    if m and m.get("significant"):
        return round(-m["slope_pct_per_c"] * heat(w.get("dew_point")), 1), "personal"
    return hadley_pct(w.get("temperature"), w.get("dew_point")), "general"


def adjust(eff: list[dict], weather: dict[int, dict], m: dict | None) -> list[dict]:
    """Heat-adjusted efficiency points (the raw value is kept as `ef_raw`)."""
    if not m or not m.get("significant"):
        return eff
    out = []
    for p in eff:
        w = weather.get(p["id"])
        factor = 1 + m["slope_pct_per_c"] / 100 * heat(w.get("dew_point")) if w else 1.0
        out.append({**p, "ef_raw": p["ef"], "ef": round(p["ef"] / max(factor, 0.5), 4)} if factor != 1.0 else p)
    return out


def outlook(hours: list[dict], day: date, start_hour: int, utc_offset: timedelta, m: dict | None) -> dict | None:
    """Conditions at your usual start time on `day`, the expected cost, and a cooler hour if it pays."""
    local = [{**h, "local": h["ts"] + utc_offset} for h in hours]
    today = [h for h in local if h["local"].date() == day and 5 <= h["local"].hour <= 21]
    if not today:
        return None
    at = min(today, key=lambda h: abs(h["local"].hour - start_hour))
    cost, basis = cost_pct(m, at)
    best = min(today, key=lambda h: (cost_pct(m, h)[0], abs(h["local"].hour - start_hour)))
    best_cost = cost_pct(m, best)[0]
    return {
        "hour": at["local"].hour, "temperature": at["temperature"], "dew_point": at["dew_point"], "apparent": at["apparent"], "wind": at["wind"],
        "cost_pct": cost, "basis": basis, "hot": hot(at),
        "better_hour": best["local"].hour if cost - best_cost >= 1.5 else None, "better_cost_pct": best_cost if cost - best_cost >= 1.5 else None,
    }


def usual_start_hour(starts: list[datetime]) -> int:
    return int(median(s.hour for s in starts)) if starts else 7
