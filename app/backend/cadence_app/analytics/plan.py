"""Periodised training plan: goal-aware phases, 3:1 load blocks, progressive key sessions and run-specific caps.

- Phases count back from a goal race: taper (1–3 weeks by distance), race-specific (6 weeks), build (8), base before.
  Without a goal, the plan builds continuously and inserts a recovery week after three building weeks.
- Weekly load: fitness (42-day CTL) rises ~2–5 points a week in building weeks (≈ 6% of current fitness), never above
  1.25 × chronic load; recovery weeks drop to ~65% (3:1 mesocycles), tapers step down 20–50%.
- Long run: +10 minutes per building week up to what the goal needs, and never more than 10% longer (by distance) than
  the longest run of the last 30 days. Single-run spikes predicted overuse injury better than weekly ratios in a
  large 2025 cohort of Garmin runners (Frandsen et al., BJSM).
- Key sessions rotate by phase and progress through each block: threshold and VO₂max intervals while building,
  race-pace work when race-specific, short sharpeners in the taper. Targets use your Garmin heart-rate zones and,
  when your critical speed is known, paces.
"""

from __future__ import annotations

from datetime import date, timedelta
from statistics import fmean

from cadence_app.analytics import athlete as A
from cadence_app.analytics import performance as P

DAY = timedelta(days=1)
CTL_WEEK_GAIN = 1 - (1 - 1 / A.CTL_DAYS) ** 7  # share of the gap to a new daily load that CTL closes in a week
GOALS = {
    "5k": {"label": "5 km", "distance_m": 5000.0, "long_min": 75, "taper_weeks": 1},
    "10k": {"label": "10 km", "distance_m": 10000.0, "long_min": 90, "taper_weeks": 1},
    "half": {"label": "Half marathon", "distance_m": 21097.5, "long_min": 120, "taper_weeks": 2},
    "marathon": {"label": "Marathon", "distance_m": 42195.0, "long_min": 165, "taper_weeks": 3},
}
GENERAL_LONG_MIN = 90
TAPER_LOAD = {1: (0.6,), 2: (0.7, 0.55), 3: (0.8, 0.65, 0.5)}
PHASES = {
    "base": ("Base", "Aerobic volume, strides and controlled threshold work."),
    "build": ("Build", "Progressive load with threshold and VO₂max sessions."),
    "specific": ("Race-specific", "Race-pace work and long runs that look like race day."),
    "recovery": ("Recovery week", "Load drops ~35% so the last three weeks turn into fitness."),
    "absorb": ("Absorb", "Your body is signalling strain: hold load down until it settles."),
    "taper": ("Taper", "Volume down, a little intensity kept: arrive fresh."),
    "race": ("Race week", "Short, sharp and rested."),
}
SPECIFIC = {
    "5k": (("5 × 1 km", "2 min jog"), ("6 × 1 km", "2 min jog"), ("4 × 1.5 km", "3 min jog")),
    "10k": (("3 × 2 km", "2 min jog"), ("4 × 2 km", "2 min jog"), ("3 × 3 km", "3 min jog")),
    "half": (("2 × 4 km", "3 min jog"), ("3 × 4 km", "3 min jog"), ("2 × 6 km", "4 min jog")),
    "marathon": (("2 × 5 km", "3 min jog"), ("3 × 5 km", "3 min jog"), ("14 km continuous", "")),
}
THRESHOLD = {"base": (("2 × 10 min", "2 min jog"), ("3 × 10 min", "2 min jog"), ("2 × 15 min", "3 min jog")),
             "build": (("3 × 8 min", "2 min jog"), ("4 × 8 min", "2 min jog"), ("3 × 12 min", "3 min jog")),
             "recovery": (("2 × 8 min", "2 min jog"),) * 3}
VO2 = (("5 × 3 min", "3 min jog"), ("5 × 4 min", "3 min jog"), ("6 × 4 min", "3 min jog"))


def _goal_phase(goal: dict, ws: date) -> dict | None:
    race_ws = A.week_start(goal["date"])
    if race_ws < ws:
        return None
    weeks_out = (race_ws - ws).days // 7
    taper = goal.get("taper_weeks") or GOALS[goal["distance"]]["taper_weeks"]  # custom goals (analytics/goals.py) carry their own
    if weeks_out == 0:
        return {"phase": "race", "week_in_block": None, "weeks_to_race": 0}
    if weeks_out <= taper:
        return {"phase": "taper", "week_in_block": taper - weeks_out + 1, "weeks_to_race": weeks_out}
    k = weeks_out - taper - 1  # 0 = the last week before the taper
    if k % 4 == 3:
        return {"phase": "recovery", "week_in_block": 4, "weeks_to_race": weeks_out}
    name = "specific" if k < 6 else "build" if k < 14 else "base"
    return {"phase": name, "week_in_block": 3 - k % 4, "weeks_to_race": weeks_out}


def phase(c: dict, ws: date) -> dict:
    """The phase of the week starting `ws`, from the goal or, without one, from the run of building weeks before it."""
    cache = c.setdefault("_phase", {})
    if ws in cache:
        return cache[ws]
    goal = c.get("goal")
    out = _goal_phase(goal, ws) if goal else None
    if out is None:
        by_week = {w["week"]: w for w in c["weeks"]}
        streak = 0
        for i in range(1, 7):
            w = by_week.get(ws - timedelta(weeks=i))
            p = c["pmc_by_day"].get(ws - timedelta(weeks=i) - DAY)
            if not w or not w["complete"] or not p or p["fitness"] <= 5:
                break
            if w["load"] < 0.85 * 7 * p["fitness"]:
                break  # a lighter week resets the block
            streak += 1
        p = c["pmc_by_day"].get(ws - DAY)
        if streak >= 3:
            out = {"phase": "recovery", "week_in_block": 4, "weeks_to_race": None}
        else:
            out = {"phase": "base" if not p or p["fitness"] < 20 else "build", "week_in_block": streak + 1, "weeks_to_race": None}
    out = {**out, "label": PHASES[out["phase"]][0], "blurb": PHASES[out["phase"]][1]}
    cache[ws] = out
    return out


def is_recovery_week(c: dict, d: date) -> bool:
    return phase(c, A.week_start(d))["phase"] in ("recovery", "taper", "race")


# ---- prescriptions -------------------------------------------------------------------------------


def _fmt_pace(s: float) -> str:
    m, sec = divmod(round(s), 60)
    return f"{m}:{sec:02d}"


def _target(kind: str, zones: dict | None, cs: dict | None, race_pace: float | None, runner: bool) -> tuple[str, list | None, list | None]:
    hr = pace = None
    if zones:
        f = zones["floors"]
        top = zones.get("max") or f[4] + 10
        lthr = zones.get("threshold") or f[4] - 1
        hr = {"threshold": [f[3], lthr], "vo2": [f[4], top], "specific": None, "hills": None, "sharpener": None, "opener": None}.get(kind)
    paces = {p["key"]: p for p in cs["paces"]} if cs and cs.get("valid") and runner else {}
    if kind == "threshold" and "threshold" in paces:
        pace = [paces["threshold"]["fast_s"], paces["threshold"]["slow_s"]]
    elif kind == "vo2" and "vo2" in paces:
        pace = [paces["vo2"]["fast_s"], paces["vo2"]["slow_s"]]
    elif kind in ("specific", "sharpener", "opener") and race_pace and runner:
        pace = [round(race_pace - 3), round(race_pace + 3)]
    parts = []
    if pace:
        parts.append(f"{_fmt_pace(pace[0])}–{_fmt_pace(pace[1])}/km")
    if hr:
        parts.append(f"{hr[0]}–{hr[1]} bpm")
    if not parts:
        parts.append({"threshold": "a comfortably hard effort (a few words at a time)", "vo2": "a hard effort you can hold evenly across reps",
                      "specific": "goal race pace", "sharpener": "goal race pace", "opener": "race pace"}.get(kind, "a controlled effort"))
    return " · ".join(parts), hr, pace


def key_sessions(ph: dict, count: int, goal: dict | None, zones: dict | None, cs: dict | None, runner: bool) -> list[dict]:
    """The week's quality sessions, in the order to do them, progressing with the week of the block."""
    if count <= 0:
        return []
    name = ph["phase"]
    i = min(max(ph.get("week_in_block") or 1, 1), 3) - 1
    distance = goal["distance"] if goal else None
    race_pace = P.pace_for(distance, cs, goal.get("target_s"), GOALS[distance]["distance_m"]) if distance else None
    unit = "run" if runner else "session"

    def make(kind: str, reps: str, rest: str, title: str) -> dict:
        text, hr, pace = _target(kind, zones, cs, race_pace, runner)
        detail = f"Warm up 15 min easy, then {reps} at {text}" + (f" with {rest} between" if rest else "") + ". Cool down 10 min."
        return {"kind": kind, "title": title, "reps": reps, "detail": detail, "hr": hr, "pace_s": pace}

    hills = {"kind": "hills", "title": "Hill sprints & strides", "reps": "8 × 10 s", "hr": None, "pace_s": None,
             "detail": f"Easy 40 min {unit}, then 8 × 10 s steep hill sprints (walk back down) and 4 × 20 s relaxed strides. "
                       "Builds power and economy without the fatigue of intervals."}
    threshold = lambda table: make("threshold", *table[i], "Threshold")  # noqa: E731
    vo2 = make("vo2", *VO2[i], "VO₂max intervals")
    options: list[dict]
    if name == "base":
        options = [threshold(THRESHOLD["base"]), hills]
    elif name == "build":
        options = [threshold(THRESHOLD["build"]), vo2]
    elif name == "specific":
        spec = make("specific", *SPECIFIC[distance][i], f"{GOALS[distance]['label']} pace") if distance else vo2
        options = [spec, threshold(THRESHOLD["build"])]
    elif name in ("recovery", "absorb"):
        options = [threshold(THRESHOLD["recovery"])]
    elif name == "taper":
        options = [make("sharpener", "4 × 1 km" if runner else "4 × 4 min", "full recovery", "Sharpener")]
    else:  # race week
        options = [make("opener", "3 × 2 min", "2 min easy", "Opener (2–3 days before)")]
    return options[:count]


def weekly_plan(c: dict) -> dict | None:
    """This week's prescription from phase, fitness, recovery signals and goal."""
    weeks = [w for w in c["weeks"] if w["complete"]][-4:]
    if len(weeks) < 2:
        return None
    as_of = c["as_of"]
    ws = A.week_start(as_of)
    ph = dict(phase(c, ws))
    latest = c["pmc"][-1] if c["pmc"] else None
    start = c["pmc_by_day"].get(ws - DAY) or latest
    ctl = start["fitness"] if start else 0.0
    fatigued = bool(latest and latest["fitness"] > 5 and latest["form"] / latest["fitness"] < -0.3)
    spiking = bool(latest and latest["acwr"] and latest["acwr"] > 1.3)
    warnings = c.get("warnings")
    hrv = c.get("hrv_guided") or {}
    absorb_why = ("illness/overreach signals" if warnings else "HRV below your normal range" if hrv.get("status") == "below"
                  else "deep fatigue" if fatigued else "a load spike" if spiking else None)
    if absorb_why and ph["phase"] not in ("recovery", "taper", "race"):
        ph.update(phase="absorb", label=PHASES["absorb"][0], blurb=f"Held back for {absorb_why}. " + PHASES["absorb"][1])
    name = ph["phase"]

    avg_load = fmean(w["load"] for w in weeks)
    chronic = 7 * ctl if ctl > 5 else avg_load
    ramp = max(2.0, min(5.0, 0.06 * ctl))
    if name in ("build", "specific", "base"):
        gain = ramp * (0.75 if name == "base" else 1.0)
        target = 7 * (ctl + gain / CTL_WEEK_GAIN) if ctl > 5 else avg_load * 1.05
        target = max(chronic, min(target, (1.2 if name == "base" else 1.25) * chronic))
        why = f"Fitness {ctl:.0f} → about {ctl + gain:.0f} by next week, capped at 1.25 × your chronic load."
    elif name == "recovery":
        target, why = 0.65 * chronic, "About 65% of your chronic load: the recovery week of a 3:1 block."
    elif name == "absorb":
        target, why = 0.75 * chronic, f"Held to ~75% of your chronic load because of {absorb_why}."
    elif name == "taper":
        steps = TAPER_LOAD[GOALS[c["goal"]["distance"]]["taper_weeks"]]
        target = steps[min(ph["week_in_block"], len(steps)) - 1] * chronic
        why = f"Taper week {ph['week_in_block']}: volume down, intensity kept."
    else:
        target, why = 0.4 * chronic, "Race week: just enough to stay sharp."
    load_band = [round(target * 0.93), round(target * 1.07)]

    sessions = int(max(3, min(7, round(fmean(w["total_sessions"] for w in weeks)))))
    if name in ("recovery", "absorb", "taper", "race"):
        sessions = max(3, sessions - 1)
    hard = {"base": 1, "build": 2 if sessions >= 4 else 1, "specific": 2 if sessions >= 4 else 1, "recovery": 1, "taper": 1, "race": 1,
            "absorb": 0 if warnings or hrv.get("status") == "below" else 1}[name]
    runs_per_week = fmean(w["sessions"].get("run", 0) for w in weeks)
    goal = c.get("goal")
    runner = runs_per_week >= 1.5 or goal is not None
    zones, cs = c.get("zones"), (c.get("performance") or {}).get("critical_speed")
    easy_cap = zones["floors"][2] - 1 if zones else None
    easy_pace = _easy_pace(c, easy_cap, cs)

    items = [
        {"label": "Weekly load", "value": f"{load_band[0]}–{load_band[1]}", "why": why + f" (4-week average {round(avg_load)})."},
        {"label": "Sessions", "value": f"{sessions}: {hard} quality, {sessions - hard} easy",
         "why": f"At least {_spacing(c)} days between quality sessions; easy days genuinely easy."},
    ]
    if easy_cap:
        items.append({"label": "Easy means", "value": f"< {easy_cap} bpm" + (f" · ~{_fmt_pace(easy_pace)}/km" if easy_pace and runner else ""),
                      "why": f"Below your Zone 3 floor ({zones['floors'][2]} bpm, {str(zones['method'] or '').replace('_', ' ').lower()} zones)."})

    long_min = long_km_cap = None
    if runner and name != "race":
        long_min, long_km_cap, long_why = _long_run(c, name, goal, easy_pace)
        if long_min:
            items.append({"label": "Long run", "value": f"1 × {long_min} min easy" + (f" · ≤ {long_km_cap:.1f} km" if long_km_cap else ""),
                          "why": long_why})
    km = [w["run_km"] for w in weeks]
    run_km = None
    if runner and fmean(km) >= 5:
        base_km = fmean(km)
        lo, hi = {"recovery": (0.6, 0.75), "absorb": (0.7, 0.85), "taper": (0.5, 0.75), "race": (0.3, 0.5)}.get(name, (0.95, 1.10))
        run_km = [round(base_km * lo), round(base_km * hi)]
        items.append({"label": "Running volume", "value": f"{run_km[0]}–{run_km[1]} km",
                      "why": "Running km grow ≤ 10% a week: tendons and bones adapt slower than heart and lungs."})
    strength = {"race": 0, "taper": 1, "recovery": 1}.get(name, 2)
    if strength:
        named = bool((c.get("strength_content") or {}).get("labelled_28d"))
        items.append({"label": "Strength", "value": f"{strength} × 30–40 min" + (" · 1 heavy lower" if named and strength >= 2 else ""),
                      "why": "Heavy, low-rep lower-body work plus calves and hips improves running economy and cuts injury risk. "
                             "Keep it away from the day before a key session."})
    items.append({"label": "Rest", "value": "≥ 1 full day", "why": "Adaptation happens during recovery."})
    need = (c.get("sleep_need") or {}).get("hours", 8.0)
    late_effect = next((e for e in c.get("effects", []) if e.id == "bed_score" and e.significant), None)
    if c.get("sleep_14"):
        tonight = c.get("tonight")
        extra = f" Tonight {tonight['tonight_h']:.1f} h, in bed by {_clock(tonight['bed_min'])}." if tonight else ""
        items.append({"label": "Sleep", "value": f"≥ {need:g} h", "why": ((c.get("sleep_need") or {}).get("detail") or "Your sleep target.") + extra})
        items.append({"label": "Lights out", "value": "≤ 23:30" if late_effect else "Consistent ±30 min",
                      "why": (f"Your sleep score averages {late_effect.reference_mean:.0f} when asleep before 23:30 vs "
                              f"{late_effect.exposed_mean:.0f} after 00:30." if late_effect else "Regular timing supports sleep quality.")})

    return {
        "focus": ph["label"],
        "phase": ph,
        "goal": _goal_view(goal),
        "items": items,
        "sessions": key_sessions(ph, hard, goal, zones, cs, runner),
        "targets": {
            "load": load_band, "sessions": sessions, "hard": hard, "easy_cap": easy_cap, "easy_pace_s": round(easy_pace) if easy_pace else None,
            "long_min": long_min, "long_km_cap": long_km_cap, "run_km": run_km, "strength": strength, "sleep_h": need,
            "lights_out_min": -30, "hard_spacing": _spacing(c),
        },
    }


def _clock(minutes: float) -> str:
    m = round(minutes) % 1440
    return f"{m // 60:02d}:{m % 60:02d}"


def _spacing(c: dict) -> int:
    return (c.get("recovery") or {}).get("hard_spacing_days", 2)


def _easy_pace(c: dict, easy_cap: int | None, cs: dict | None) -> float | None:
    t = c.get("eff_trend")
    if t and easy_cap and t.get("rhr") is not None and easy_cap > t["rhr"]:
        return t["pace_now_s"] * (t["ref_hr"] - t["rhr"]) / (easy_cap - t["rhr"])
    if cs and cs.get("valid"):
        easy = next(p for p in cs["paces"] if p["key"] == "easy")
        return (easy["slow_s"] + easy["fast_s"]) / 2
    return None


def _long_run(c: dict, name: str, goal: dict | None, easy_pace: float | None) -> tuple[int | None, float | None, str]:
    as_of = c["as_of"]
    need = GOALS[goal["distance"]]["long_min"] if goal else GENERAL_LONG_MIN
    recent = [w for w in c["weeks"] if w["complete"]][-3:]
    longest = max((w.get("long_run_min", 0) for w in recent), default=0)
    if name in ("recovery", "absorb"):
        minutes, why = max(45, 0.75 * max(longest, 60)), "Shortened by a quarter for the lighter week."
    elif name == "taper":
        minutes, why = 0.6 * need, "Trimmed for the taper; keep it relaxed."
    else:
        minutes = min(need, max(60, longest + 10))
        why = (f"Up 10 min from your recent longest ({longest:.0f} min), building toward {need} min" + (f" for the {GOALS[goal['distance']]['label'].lower()}." if goal else ".")
               if minutes < need else f"At your goal duration of {need} min: hold it here.")
    prior = [a.distance_m for a in c["acts"] if a.family == "run" and a.distance_m and as_of - timedelta(days=30) <= a.day <= as_of]
    cap_km = round(max(prior) * 1.10 / 1000, 1) if len(prior) >= 3 else None
    if cap_km and easy_pace:
        cap_min = cap_km * easy_pace / 60
        if cap_min < minutes:
            minutes = cap_min
            why += f" Capped so it's no more than 10% longer than your longest run of the last 30 days ({max(prior) / 1000:.1f} km)."
    return int(round(minutes / 5) * 5), cap_km, why


def _goal_view(goal: dict | None) -> dict | None:
    if not goal:
        return None
    g = GOALS[goal["distance"]]
    return {"distance": goal["distance"], "label": g["label"], "date": goal["date"], "target_s": goal.get("target_s"),
            "target_pace_s": round(goal["target_s"] / g["distance_m"] * 1000) if goal.get("target_s") else None}
