"""Session planner: what to do on a given day, by sport, and what each option will do to you.

- Load estimate: your own load per minute on similar past sessions (same sport and effort) × the planned minutes.
  A zone model (weights per heart-rate-zone minute, non-decreasing Z1→Z5, fitted as non-negative increments) only
  adjusts that for the planned intensity (×0.6–1.6, when it explains your loads reasonably), and stands in when a
  sport has fewer than 3 similar sessions. Garmin's load is EPOC-based, so zone minutes alone fit it loosely.
- Outcomes: the predicted load is run through the same fitness/fatigue model (and readiness load formula) as your
  history, together with anything else already planned that week, to give tomorrow morning's numbers.
- Ranking: readiness (known today; assumed normal for later days), HRV-guided status, early-warning signals, your
  personal spacing between hard sessions (counting planned ones), the week's open targets, and no heavy legs next to
  a key run.
"""

from __future__ import annotations

import re
from datetime import date, timedelta
from statistics import median

import numpy as np
from scipy.optimize import nnls

from cadence_app.analytics import athlete as A
from cadence_app.analytics import heat as W
from cadence_app.analytics import performance as P
from cadence_app.analytics import plan as training_plan

DAY = timedelta(days=1)
SPORTS = ("run", "ride", "swim", "strength")
HARD_KINDS = {"threshold", "vo2", "specific", "hills", "tempo", "sprints", "sharpener", "opener"}
LONG_KINDS = {"long"}
FALLBACK_WEIGHTS = [0.3, 0.8, 1.5, 2.4, 3.4]  # load per minute in Z1..Z5 until your own fit exists
BUILDS = {
    "recovery": "Circulation and an easier tomorrow; no fitness gain, and that's the point.",
    "easy": "Aerobic base: mitochondria, capillaries and fat use. Most of your fitness comes from these.",
    "long": "Durability and endurance: holding pace late, fuelling, tendons ready for longer efforts.",
    "threshold": "Lactate threshold: the effort you can hold for about an hour.",
    "vo2": "VO₂max: your aerobic ceiling, which lifts every pace beneath it.",
    "hills": "Power and running economy, with little fatigue.",
    "specific": "Race-pace confidence and economy at goal pace.",
    "sharpener": "Keeps race pace sharp while the taper sheds fatigue.",
    "opener": "Primes legs and nerves for race day.",
    "tempo": "Sustained aerobic power just below threshold.",
    "technique": "Stroke efficiency: cheaper swimming at every pace.",
    "sprints": "Speed and neuromuscular power.",
    "strength": "Force, tendon stiffness and injury resistance; better running economy over weeks.",
}


# ---- personal load model -------------------------------------------------------------------


def load_model(acts: list[A.Act], as_of: date) -> dict:
    rows = [a for a in acts if len(a.zones_s) >= 5 and a.load > 0 and as_of - timedelta(days=365) < a.day <= as_of]
    if len(rows) >= 15:
        X = np.array([[z / 60 for z in a.zones_s] for a in rows])
        y = np.array([a.load for a in rows])
        # Weights must not fall from one zone to the next (a harder minute never costs less), else zones your data
        # can't separate get zero and a VO2 session predicts almost nothing. Fit non-negative increments instead:
        # w_z = d_1 + … + d_z, d ≥ 0, i.e. NNLS on cumulative "minutes at zone ≥ j" columns.
        cumulative = np.cumsum(X[:, ::-1], axis=1)[:, ::-1]
        d, _ = nnls(cumulative, y)
        w = np.cumsum(d)
        pred = X @ w
        spread = float(np.sum((y - y.mean()) ** 2))
        r2 = 1 - float(np.sum((y - pred) ** 2)) / spread if spread > 0 else 0.0  # identical loads explain nothing
        weights = [round(float(x), 3) for x in w] if r2 > 0.3 else FALLBACK_WEIGHTS
    else:
        weights, r2 = FALLBACK_WEIGHTS, 0.0
    factors, counts = {}, {}
    for sport in ("run", "ride", "swim", "strength"):
        xs = [a for a in rows if a.family == sport]
        counts[sport] = len(xs)
        ratios = [a.load / p for a in xs if (p := sum(w * z / 60 for w, z in zip(weights, a.zones_s))) > 5]
        # Capped: a sport the zone model barely explains (few, odd sessions) mustn't blow up its predictions.
        factors[sport] = round(min(2.0, max(0.5, median(ratios))), 3) if len(ratios) >= 5 else 1.0
    return {"weights": weights, "factors": factors, "counts": counts, "r2": round(r2, 2), "n": len(rows)}


def predict_load(model: dict, sport: str, profile: list[float]) -> float:
    return sum(w * m for w, m in zip(model["weights"], profile)) * model["factors"].get(sport, 1.0)


def estimate_load(model: dict, option: dict, similar: list[A.Act]) -> tuple[float, str]:
    """(load, basis): from similar sessions per minute, adjusted by the zone model; else the model; else general."""
    sport, profile, minutes = option["sport"], option.get("profile"), option.get("minutes") or 0
    rates = [a.load / (a.moving_s / 60) for a in similar if a.moving_s and a.moving_s >= 600]
    if not profile:  # strength: whole classes, not per minute
        return (median([a.load for a in similar]), "similar") if similar else (60.0, "general")
    usable = model["r2"] >= 0.3
    planned = predict_load(model, sport, profile)
    if len(rates) >= 3:
        base = median(rates) * minutes
        adj = 1.0
        if usable:
            typical = [predict_load(model, sport, [z / 60 for z in a.zones_s]) / (a.moving_s / 60) for a in similar
                       if len(a.zones_s) >= 5 and a.moving_s]
            ref = median(typical) * minutes if typical else 0.0
            if ref > 5 and planned > 5:
                adj = min(1.6, max(0.6, planned / ref))
        return base * adj, "similar"
    if usable and planned > 5:
        return planned, "model"
    return sum(w * m for w, m in zip(FALLBACK_WEIGHTS, profile)), "general"


# ---- session library --------------------------------------------------------------------------


def _profile(*parts: tuple[float, int]) -> list[float]:
    """(minutes, zone 1-5) pieces → minutes per zone."""
    out = [0.0] * 5
    for minutes, zone in parts:
        out[zone - 1] += minutes
    return out


def _reps(reps: str, pace_s: float | None) -> tuple[float, int]:
    """'3 × 8 min' → (3, 8.0); '5 × 1 km' → minutes at race pace; '14 km continuous' → one rep."""
    m = re.match(r"(\d+)\s*×\s*([\d.]+)\s*(min|km|s)", reps)
    if not m:
        m2 = re.match(r"([\d.]+)\s*km", reps)
        return ((float(m2.group(1)) * (pace_s or 300) / 60) if m2 else 20.0), 1
    n, size, unit = int(m.group(1)), float(m.group(2)), m.group(3)
    minutes = size if unit == "min" else size / 60 if unit == "s" else size * (pace_s or 300) / 60
    return minutes, n


def _rest_minutes(text: str) -> float:
    m = re.search(r"(\d+)\s*min", text or "")
    return float(m.group(1)) if m else 2.0


def run_options(c: dict, plan: dict | None) -> list[dict]:
    t = (plan or {}).get("targets", {})
    cap = t.get("easy_cap")
    easy_txt = f"under {cap} bpm" if cap else "at a conversational effort"
    easy_runs = [a.moving_s / 60 for a in c["acts"] if a.family == "run" and a.moving_s and a.day > c["as_of"] - timedelta(days=60)
                 and (k := A.intensity(a)) and k["kind"] == "easy"]
    easy_min = int(min(60, max(30, round(median(easy_runs) / 5) * 5))) if easy_runs else 40
    long_min = t.get("long_min") or 75
    out = [
        {"key": "run_recovery", "sport": "run", "kind": "recovery", "title": "Recovery jog · 25 min", "minutes": 25,
         "detail": f"Very easy, {easy_txt}; walk breaks are fine.", "profile": _profile((25, 1))},
        {"key": "run_easy", "sport": "run", "kind": "easy", "title": f"Easy run · {easy_min} min", "minutes": easy_min,
         "detail": f"Conversational, {easy_txt}. Add 4 × 20 s relaxed strides at the end if you feel good.", "profile": _profile((5, 1), (easy_min - 5, 2))},
        {"key": "run_long", "sport": "run", "kind": "long", "title": f"Long run · {long_min} min", "minutes": long_min,
         "detail": f"Easy, {easy_txt}" + (f", no more than {t['long_km_cap']:.1f} km" if t.get("long_km_cap") else "")
                   + ". Start slower than feels necessary; take carbs after the first hour.",
         "profile": _profile((10, 1), (long_min - 10, 2))},
    ]
    goal = c.get("goal")
    cs = (c.get("performance") or {}).get("critical_speed")
    race_pace = None
    if goal:
        g = training_plan.GOALS[goal["distance"]]
        race_pace = P.pace_for(goal["distance"], cs, goal.get("target_s"), g["distance_m"])
    phase = dict((plan or {}).get("phase") or {"phase": "build", "week_in_block": 1})
    if phase["phase"] in ("absorb", "race"):
        phase["phase"] = "build"
    quality = training_plan.key_sessions(phase, 2, goal, c.get("zones"), cs, True)
    extra = [k for k in ("threshold", "vo2", "hills") if k not in {q["kind"] for q in quality}]
    for kind in extra:
        alt = training_plan.key_sessions({**phase, "phase": {"threshold": "build", "vo2": "build", "hills": "base"}[kind]}, 2, goal, c.get("zones"), cs, True)
        quality += [q for q in alt if q["kind"] == kind][:1]
    zone_of = {"threshold": 4, "vo2": 5, "specific": 4, "sharpener": 4, "opener": 4, "hills": 5}
    for q in quality:
        if q["kind"] == "hills":
            profile, minutes = _profile((5, 1), (35, 2), (3, 5)), 45
        else:
            rep_min, n = _reps(q["reps"], race_pace)
            rest = _rest_minutes(q["detail"].split(" with ")[-1]) if " with " in q["detail"] else 2.0
            work = rep_min * n
            minutes = round(15 + work + rest * max(0, n - 1) + 10)
            profile = _profile((10, 1), (5, 2), (work, zone_of.get(q["kind"], 4)), (rest * max(0, n - 1), 1), (10, 1))
        out.append({"key": f"run_{q['kind']}", "sport": "run", "kind": q["kind"], "title": f"{q['title']} · {q['reps']}", "minutes": minutes,
                    "detail": q["detail"], "profile": profile})
    return out


def ride_options(c: dict) -> list[dict]:
    z = (c.get("zones") or {}).get("floors")
    hr = (lambda lo, hi: f"{lo - 5}–{hi - 5} bpm") if z else (lambda lo, hi: "")
    zone = lambda i: hr(z[i - 1], (z[i] if i < 5 else (c["zones"].get("max") or z[4] + 15))) if z else ""  # noqa: E731
    note = " (cycling HR runs about 5 bpm below running)" if z else ""
    return [
        {"key": "ride_recovery", "sport": "ride", "kind": "recovery", "title": "Recovery spin · 40 min", "minutes": 40,
         "detail": f"Light gears, high cadence, {zone(1) or 'very easy'}{note}.", "profile": _profile((40, 1))},
        {"key": "ride_endurance", "sport": "ride", "kind": "easy", "title": "Endurance ride · 90 min", "minutes": 90,
         "detail": f"Steady {zone(2) or 'conversational'}{note}. Eat 30–60 g carbs an hour.", "profile": _profile((10, 1), (80, 2))},
        {"key": "ride_long", "sport": "ride", "kind": "long", "title": "Long ride · 150 min", "minutes": 150,
         "detail": f"Mostly {zone(2) or 'easy'}; fuel from the start.", "profile": _profile((15, 1), (135, 2))},
        {"key": "ride_tempo", "sport": "ride", "kind": "tempo", "title": "Tempo · 2 × 20 min", "minutes": 75,
         "detail": f"Warm up 15 min, then 2 × 20 min at {zone(3) or 'comfortably hard'} with 5 min easy. Cool down 10 min.",
         "profile": _profile((15, 1), (40, 3), (5, 1), (15, 1))},
        {"key": "ride_threshold", "sport": "ride", "kind": "threshold", "title": "Threshold · 3 × 10 min", "minutes": 70,
         "detail": f"Warm up 15 min, then 3 × 10 min at {zone(4) or 'hard, sustainable'} with 5 min easy. Cool down 15 min.",
         "profile": _profile((15, 1), (30, 4), (10, 1), (15, 1))},
        {"key": "ride_vo2", "sport": "ride", "kind": "vo2", "title": "VO₂max · 5 × 4 min", "minutes": 60,
         "detail": f"Warm up 15 min, then 5 × 4 min at {zone(5) or 'very hard'} with 4 min easy. Cool down 10 min.",
         "profile": _profile((15, 1), (20, 5), (16, 1), (10, 1))},
    ]


def swim_options() -> list[dict]:
    feel = "Wrist heart rate is unreliable in water, so go by feel."
    return [
        {"key": "swim_technique", "sport": "swim", "kind": "technique", "title": "Technique · 30 min", "minutes": 30,
         "detail": f"200 easy, 8 × 50 drill/swim (catch-up, fingertip drag) with 20 s rest, 200 easy pull. {feel}", "profile": _profile((10, 1), (20, 2))},
        {"key": "swim_aerobic", "sport": "swim", "kind": "easy", "title": "Aerobic · 45 min", "minutes": 45,
         "detail": f"300 warm-up, 3 × 400 steady (could talk between lengths) with 30 s rest, 200 cool-down. {feel}", "profile": _profile((10, 1), (35, 2))},
        {"key": "swim_threshold", "sport": "swim", "kind": "threshold", "title": "Threshold · 10 × 100", "minutes": 45,
         "detail": f"400 warm-up, 10 × 100 at a hard, even pace with 15 s rest (same time every rep), 200 cool-down. {feel}",
         "profile": _profile((12, 1), (5, 2), (20, 4), (8, 1))},
        {"key": "swim_sprints", "sport": "swim", "kind": "sprints", "title": "Sprints · 12 × 25", "minutes": 35,
         "detail": f"400 warm-up, 12 × 25 fast with 40 s rest, 300 easy. {feel}", "profile": _profile((15, 1), (8, 2), (5, 5), (7, 1))},
    ]


def strength_option(c: dict, blocks: list[dict] | None = None, summary: dict | None = None) -> dict:
    heavy = bool(summary and summary.get("heavy_lower"))
    return {"key": "strength_class", "sport": "strength", "kind": "strength", "title": "Strength class" + (" · heavy lower body" if heavy else ""),
            "minutes": 50, "detail": "From your screenshot." if blocks else "Upload the class screenshot to plan its content.",
            "profile": None, "heavy_lower": heavy, "blocks": blocks or []}


# ---- outcomes ----------------------------------------------------------------------------------


def _effort(kind: str) -> str:
    return "hard" if kind in HARD_KINDS else "long" if kind in LONG_KINDS else "easy"


def _similar(c: dict, sport: str, kind: str, heavy: bool | None = None, effort: str | None = None) -> list[A.Act]:
    as_of = c["as_of"]
    effort = effort or _effort(kind)
    out = []
    for a in c["acts"]:
        if a.family != sport or a.day <= as_of - timedelta(days=180) or a.load <= 0:
            continue
        if sport == "strength":
            label = c.get("labels", {}).get(a.id)
            if heavy is None or (label and label["summary"]["heavy_lower"] == heavy):
                out.append(a)
            continue
        is_long = (a.moving_s or 0) >= A.LONG_MIN.get(sport, 10**6) * 60
        mine = "hard" if A.is_hard(a) else "long" if is_long else "easy"
        if mine == effort:
            out.append(a)
    return out


def predict(c: dict, model: dict, day: date, option: dict, planned: list[dict]) -> dict:
    """What this option does: load, strain, tomorrow's fitness/form/readiness, recovery and what it builds."""
    sport, kind = option["sport"], option["kind"]
    similar = _similar(c, sport, kind, option.get("heavy_lower") if sport == "strength" else None)
    load, basis = estimate_load(model, option, similar)
    if basis not in ("similar",) and sport != "strength":
        # Fewer than 3 like sessions: long/recovery share easy intensity (rate per minute), then the same effort in
        # your other endurance sports, before falling back to the zone model.
        chain = []
        if _effort(kind) in ("long", "easy"):
            chain.append((_similar(c, sport, kind, effort="easy"), "similar"))
        chain.append(([a for other in ("run", "ride", "swim") if other != sport for a in _similar(c, other, kind)], "other sports"))
        for pool, label in chain:
            est, how = estimate_load(model, option, pool)
            if how == "similar":
                load, basis = est, label
                break
    hist = [a.load for a in similar]
    te = [a.aerobic_te for a in similar if a.aerobic_te]
    as_of = c["as_of"]

    def tomorrow(with_this: bool) -> dict | None:
        loads = dict(c["load"])
        for p in planned:
            if as_of < p["day"] and p["predicted_load"] and not (p["day"] == day and p.get("id") == option.get("id")):
                loads[p["day"]] = loads.get(p["day"], 0.0) + p["predicted_load"]
        if with_this:
            loads[day] = loads.get(day, 0.0) + load
        rows = A.pmc(loads, c["first"], day + DAY)
        return rows[-1] if rows else None

    after, before = tomorrow(True), tomorrow(False)
    rec = (c.get("recovery") or {}).get("kinds", {}).get(_effort(kind) if sport != "strength" else ("hard" if option.get("heavy_lower") else "easy"), {})
    strain = (c.get("strain") or {}).get("days", {})
    everyday = median([v["everyday"] for d, v in strain.items() if as_of - timedelta(days=28) <= d < as_of]) if strain else 0.0
    so_far = strain.get(as_of, {}).get("total", 0.0) if day == as_of else everyday
    outlook = W.outlook(c["forecast"], day, c.get("start_hour", 7), c["utc_offset"], c.get("heat")) \
        if sport in ("run", "ride") and c.get("forecast") else None
    return {
        "weather": outlook,
        "load": round(load),
        "load_range": [round(min(hist)), round(max(hist))] if len(hist) >= 3 else None,
        "similar_n": len(similar),
        "similar_load": round(median(hist)) if hist else None,
        "aerobic_te": round(median(te), 1) if len(te) >= 3 else None,
        "day_strain": round(so_far + load) if strain else None,
        "fitness": [round(before["fitness"], 1), round(after["fitness"], 1)] if after and before else None,
        "form_tomorrow": round(after["form"], 1) if after else None,
        "acwr_tomorrow": after["acwr"] if after else None,
        "readiness_load": [round(A.load_score(before)), round(A.load_score(after))] if after and before and after["fitness"] > 5 else None,
        "recovery_days": rec.get("days"),
        "recovery_personal": bool(rec.get("personal")),
        "builds": BUILDS.get(kind, BUILDS.get(_effort(kind), "")) + (" Raises your critical speed most directly." if sport == "run" and kind == "threshold" else ""),
        "basis": basis,
        "confidence": "personal" if basis in ("similar", "model", "other sports") else "general",
    }


# ---- ranking -----------------------------------------------------------------------------------


def _hard_days(c: dict, planned: list[dict], skip_id: int | None = None) -> set[date]:
    days = {a.day for a in c["acts"] if A.is_hard(a)}
    days |= {p["day"] for p in planned if p.get("id") != skip_id and (_effort(p["kind"]) == "hard" or p.get("heavy_lower"))}
    return days


def rank(c: dict, day: date, options: list[dict], planned: list[dict], readiness: dict | None) -> list[dict]:
    """Adds `recommended`, `why` and `caution` to each option; the best fit for the day goes first."""
    as_of = c["as_of"]
    plan = training_plan.weekly_plan(c)
    t = (plan or {}).get("targets", {})
    spacing = (c.get("recovery") or {}).get("hard_spacing_days", 2)
    hard_days = _hard_days(c, planned)
    near_hard = any(abs((d - day).days) < spacing and d != day for d in hard_days)
    same_day_hard = any(p["day"] == day and (_effort(p["kind"]) == "hard" or p.get("heavy_lower")) for p in planned) \
        or any(a.day == day and A.is_hard(a) for a in c["acts"])
    ws = A.week_start(day)
    week_hard = sum(1 for d in hard_days if ws <= d < ws + timedelta(days=7))
    week_long = any(a.family == "run" and ws <= a.day < ws + timedelta(days=7) and (a.moving_s or 0) >= (t.get("long_min") or 75) * 0.9 * 60 for a in c["acts"]) \
        or any(p["kind"] == "long" and ws <= p["day"] < ws + timedelta(days=7) for p in planned)
    key_run_next = any(p["sport"] == "run" and _effort(p["kind"]) in ("hard", "long") and p["day"] in (day + DAY, day - DAY) for p in planned) \
        or any(a.family == "run" and (A.is_hard(a)) and a.day == day - DAY for a in c["acts"])
    today = day == as_of
    score = readiness["score"] if (today and readiness) else None
    warn = c.get("warnings") if today else None
    hrv_low = today and (c.get("hrv_guided") or {}).get("status") == "below"
    for o in options:
        effort = _effort(o["kind"])
        s, why, caution = 50.0, [], None
        if o["kind"] == "recovery":
            s += 30 if (warn or (score is not None and score < 50)) else -15
            why.append("Keeps you moving while your body catches up." if (warn or (score or 100) < 50) else "Only if you need an easy day.")
        if effort == "hard" or o.get("heavy_lower"):
            if warn or hrv_low or (score is not None and score < 70):
                s -= 60
                caution = "Recovery signals are low today: keep intensity for a better day."
            elif same_day_hard:
                s -= 50
                caution = "There's already a hard session on this day: one is enough."
            elif near_hard:
                s -= 40
                caution = f"Less than {spacing} days from another hard session."
            elif o.get("heavy_lower") and key_run_next:
                s -= 30
                caution = "A key run sits next to this day: heavy legs would cost that run."
            elif t.get("hard") is not None and week_hard >= t["hard"] and o["sport"] == "run":
                s -= 25
                caution = f"This week's {t['hard']} quality session{'s are' if t['hard'] != 1 else ' is'} already planned or done."
            else:
                s += 25 + (10 if score is not None and score >= 85 else 0)
                why.append("You're fresh enough and it's been long enough since the last hard day." if score is not None else "Fits the week's spacing.")
        if effort == "long":
            if warn:
                s -= 40
                caution = "Not on a day your body is flagging illness or overreaching."
            elif same_day_hard:
                s -= 45
                caution = "There's already a hard session on this day: save the long one for another."
            elif not week_long and o["sport"] == "run" and t.get("long_min"):
                s += 20 + (10 if day.weekday() >= 5 else 0)
                why.append("This week's long run is still open.")
            else:
                s -= 10
        if effort == "easy" and o["kind"] not in ("recovery",):
            s += 15 if (near_hard or (score is not None and score < 70)) else 5
            why.append("The volume that builds your base without taxing recovery.")
        o.update(score=s, why=" ".join(why) or None, caution=caution)
    options.sort(key=lambda o: -o["score"])
    for i, o in enumerate(options):
        o["recommended"] = i == 0 and not o["caution"]
    return options


def projection(c: dict) -> dict | None:
    """Fitness in 4 weeks if each week lands mid-way in the plan's load band (recovery weeks included)."""
    plan = training_plan.weekly_plan(c)
    if not plan or not c["pmc"]:
        return None
    lo, hi = plan["targets"]["load"]
    weekly = (lo + hi) / 2
    loads = dict(c["load"])
    start = c["as_of"] + DAY
    for i in range(28):
        d = start + timedelta(days=i)
        loads[d] = weekly / 7 * (0.65 if (i // 7) == 3 and plan["phase"]["phase"] not in ("recovery", "taper") else 1.0)
    rows = A.pmc(loads, c["first"], start + timedelta(days=27))
    return {"fitness_now": c["pmc"][-1]["fitness"], "fitness_4w": rows[-1]["fitness"], "weekly_load": round(weekly)}
