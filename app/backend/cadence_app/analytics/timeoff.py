"""Time off and plan settings: how travel, holidays, illness and injury change a week's targets, and how you ease back.

- A day's availability is 0 when you are ill or injured, 0 when away and not training, a share (default 40%) when away and
  doing light movement, and 1 when away but training as normal. A week's targets scale by its mean availability, so a
  3-day trip asks for ~3/7 of the load and is not a miss.
- After a break the load returns on a ramp, not in one step: it starts at a share of your pre-break load and climbs
  linearly back to 100% over the return weeks. Defaults follow common return-to-training guidance (a graded return that
  starts at roughly half the usual load after a moderate illness, with a longer, lower start after a severe one) and are
  yours to change: `severity` (how bad it felt) scales the defaults and every number can be overridden per entry.
  Fitness (a 42-day average) falls by about a quarter over two weeks off, which is why the ramp is anchored on the load
  from before the break and not on today's lower fitness (Mujika & Padilla 2000, detraining after short breaks).
- A genuine break (a week at under half availability) counts as the block's recovery week; a lighter interruption neither
  breaks nor extends a building block.
- Nothing here is medical advice: after illness with fever, chest symptoms or anything unusual, ask a clinician before returning.
"""

from __future__ import annotations

from datetime import date, timedelta
from statistics import fmean

DAY = timedelta(days=1)
KINDS = ("travel", "vacation", "sick", "injury")
ACTIVITIES = ("none", "light", "full")
LIGHT_SHARE = 0.4  # availability on a day away doing light movement

# name: (default, lowest, highest). Stored as one JSON object in app_settings.
SETTINGS = {
    "ramp_pct": (5.0, 2.0, 8.0),  # weekly fitness gain while building, % of current fitness
    "build_weeks": (3.0, 2.0, 4.0),  # building weeks before a recovery week
    "deload_pct": (65.0, 50.0, 85.0),  # a recovery week's load as % of your chronic load
    "away_activity": ("light", None, None),  # what you usually do while travelling or on holiday
    "away_return_weeks": (1.0, 0.0, 4.0),  # easing back after 4+ days away without training
    "away_return_pct": (90.0, 50.0, 100.0),  # ...starting at this % of your pre-trip load
    "sick_return_weeks": (2.0, 0.0, 8.0),  # easing back after a moderate illness or injury
    "sick_return_pct": (50.0, 20.0, 100.0),  # ...starting at this % of your pre-illness load
}
DEFAULTS = {k: v[0] for k, v in SETTINGS.items()}
SEVERITY_WEEKS = {1: 0.5, 2: 1.0, 3: 1.5}  # multiplies sick_return_weeks (mild 1 week, moderate 2, severe 3 by default)
SEVERITY_START = {1: 1.4, 2: 1.0, 3: 0.7}  # multiplies sick_return_pct (mild 70%, moderate 50%, severe 35%)
MIN_AWAY_DAYS_TO_EASE = 4
OFF_BELOW = 0.3  # a week with under this share of days available is "time off" (5 or more days lost)


def clean_settings(raw: dict | None) -> dict:
    """Stored values clamped to their range; anything missing or invalid falls back to the default."""
    out = dict(DEFAULTS)
    for key, (default, lo, hi) in SETTINGS.items():
        v = (raw or {}).get(key)
        if key == "away_activity":
            out[key] = v if v in ACTIVITIES else default
        elif isinstance(v, (int, float)) and not isinstance(v, bool):
            out[key] = min(hi, max(lo, float(v)))
    out["build_weeks"] = round(out["build_weeks"])
    return out


def span(p: dict, today: date) -> tuple[date, date]:
    """First and last day of an entry; an open one runs to today (or its start, if that is still ahead)."""
    return p["start"], p["end"] or max(today, p["start"])


def resolve(p: dict, cfg: dict) -> dict:
    """The numbers an entry actually uses: its own settings, else yours scaled by how it felt."""
    if p["kind"] in ("sick", "injury"):
        sev = p.get("severity") or 2
        weeks = p.get("return_weeks")
        start = p.get("return_start_pct")
        weeks = round(cfg["sick_return_weeks"] * SEVERITY_WEEKS[sev]) if weeks is None else weeks
        start = min(95, round(cfg["sick_return_pct"] * SEVERITY_START[sev])) if start is None else start
        return {"weight": 0.0, "return_weeks": int(weeks), "return_start": start / 100, "activity": "none"}
    activity = p.get("activity") or cfg["away_activity"]
    weight = {"none": 0.0, "light": LIGHT_SHARE, "full": 1.0}[activity]
    weeks = p.get("return_weeks")
    start = p.get("return_start_pct")
    weeks = cfg["away_return_weeks"] if weeks is None else weeks
    start = cfg["away_return_pct"] if start is None else start
    return {"weight": weight, "return_weeks": int(weeks) if activity != "full" else 0, "return_start": start / 100, "activity": activity}


def day_factors(periods: list[dict], cfg: dict, today: date, day: date) -> tuple[float, float, dict | None]:
    """(availability, return factor, entry) for one day. Overlapping entries take the most restrictive of each."""
    weight, ret, owner = 1.0, 1.0, None
    for p in periods:
        first, last = span(p, today)
        r = resolve(p, cfg)
        if first <= day <= last:
            if r["weight"] < weight:
                weight, owner = r["weight"], p
        elif day > last and r["return_weeks"] > 0 and (p["kind"] in ("sick", "injury") or (last - first).days + 1 >= MIN_AWAY_DAYS_TO_EASE):
            span_days = 7 * r["return_weeks"]
            t = ((day - last).days - 1) / span_days
            if t < 1:
                f = r["return_start"] + (1 - r["return_start"]) * t
                if f < ret:
                    ret = f
                    owner = owner or p
    return weight, ret, owner


def week_scale(periods: list[dict], cfg: dict, today: date, ws: date) -> dict:
    """How a week's targets scale: `availability` (days you can train), `ret` (the easing-back ramp) and their product `scale`."""
    if not periods:
        return {"scale": 1.0, "availability": 1.0, "ret": 1.0, "days_off": 0, "entries": []}
    rows = [day_factors(periods, cfg, today, ws + timedelta(days=i)) for i in range(7)]
    availability = fmean(w for w, _, _ in rows)
    ret = fmean(r for _, r, _ in rows)
    scale = fmean(w * r for w, r, _ in rows)
    ids = []
    for _, _, p in rows:
        if p is not None and p["id"] not in ids:
            ids.append(p["id"])
    return {"scale": round(scale, 3), "availability": round(availability, 3), "ret": round(ret, 3),
            "days_off": sum(1 for w, _, _ in rows if w < 1), "entries": ids}


def pre_break_day(periods: list[dict], cfg: dict, today: date, ws: date) -> date | None:
    """The day before the most recent break that is still easing back (or running) in the week starting `ws`."""
    best = None
    for p in periods:
        first, last = span(p, today)
        weeks = resolve(p, cfg)["return_weeks"]
        if first <= ws + 6 * DAY and last + timedelta(weeks=weeks) >= ws and (best is None or first > best):
            best = first
    return best - DAY if best else None


def is_break(scale: dict) -> bool:
    """A week mostly lost to time off: it stands in for the block's recovery week."""
    return scale["scale"] < 0.5


def describe(p: dict, cfg: dict, today: date) -> dict:
    """An entry with the numbers it uses, for the UI."""
    first, last = span(p, today)
    r = resolve(p, cfg)
    return {**p, "ongoing": p["end"] is None, "days": (last - first).days + 1, "uses": {
        "activity": r["activity"], "return_weeks": r["return_weeks"], "return_start_pct": round(r["return_start"] * 100)}}
