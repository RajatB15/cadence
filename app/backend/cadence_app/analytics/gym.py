"""Gym planner engine: exercise library, equipment, swaps, session structure, time estimates and rule-based generation.

Pure functions only (no database, no clock); storage is `gym_store.py`, wording of plans stays with the user. Rule-based, no model.

Library (`gym_library.json`, written for this project in our own words): per exercise a movement pattern (the same fourteen
categories as `exercises.json`, so a planned session still parses and counts toward the weekly pattern notes), a progression
`family` and `level` 1-5, equipment as alternatives (each alternative lists what is needed together), muscles, how-to cues and
common mistakes. Technique notes in the style of the NSCA's *Essentials of Strength and Conditioning* and ACSM guidance; not
medical advice.

Swaps: easier / harder walk the family ladder (same idea, one level down / up), falling back to the same pattern with overlapping
primary muscles; different keeps pattern and muscles but changes the family. Candidates are ranked by transparent rules (same family,
muscle overlap, level distance) and always filtered to the equipment available. Nothing is chosen for you.

Generation: a template (full body, upper, lower, ...) fills slots by movement pattern and equipment from a seeded shuffle, with a
conventional structure (warm-up, main lifts, accessories, core, finisher) and set/rep ranges by goal (strength 3-5 x 3-6, muscle
8-12 x 3-4, endurance 12-20 x 2-3; NSCA/ACSM resistance-training ranges). There is no load recommendation: we don't know your
maximums, so load is left for you. Time estimates are rough (reps x ~3 s plus rest, mode paces for cardio); they are labelled estimates.

Hyrox: eight rounds of a 1 km run then a station in fixed order (SkiErg 1000 m, sled push 50 m, sled pull 50 m, burpee broad jumps
80 m, rowing 1000 m, farmers carry 200 m, sandbag lunges 100 m, wall balls 100 reps). Station loads vary by division and sources
disagree, so templates leave loads blank for you to set from the current official rulebook.
"""

from __future__ import annotations

import json
import random
import re
from functools import lru_cache
from pathlib import Path

LIB_FILE = Path(__file__).with_name("gym_library.json")
SETTINGS = ("gym", "home")
LEVELS = {"beginner": (1, 2), "intermediate": (2, 3), "advanced": (3, 5)}
GOALS = ("general", "strength", "muscle", "endurance")
MAX_DEPTH, MAX_STEPS = 3, 200
BODYWEIGHT = "bodyweight"
EQUIVALENT = {"bench": "box", "box": "bench"}  # a sturdy surface does for either
LIFT_PATTERNS = {"squat", "hinge", "lunge", "push", "pull"}
NO_CROSSOVER = {"mobility", "drill", "cardio"}  # warm-up, mobility and conditioning work is only ever replaced by its own kind


class GymError(ValueError):
    pass


# --------------------------------------------------------------------- library
@lru_cache(maxsize=1)
def library() -> dict:
    doc = json.loads(LIB_FILE.read_text(encoding="utf-8"))
    by_id = {e["id"]: e for e in doc["exercises"]}
    return {"equipment": doc["equipment"], "exercises": doc["exercises"], "by_id": by_id}


def exercise(ex_id: str) -> dict | None:
    return library()["by_id"].get(ex_id)


def equipment_names() -> list[str]:
    return [e for e in library()["equipment"] if e != BODYWEIGHT]


def owned_set(setting: str, home_equipment: list[str] | None) -> set[str]:
    """Everything for the gym; for home, only what you said you own (bodyweight always)."""
    if setting == "gym":
        return set(library()["equipment"]) - {"backpack"}  # a gym has the real kit; a loaded backpack is a home stand-in
    owned = {BODYWEIGHT} | {e for e in (home_equipment or []) if e in library()["equipment"]}
    return owned | {EQUIVALENT[e] for e in owned if e in EQUIVALENT}


def available(ex: dict, owned: set[str]) -> bool:
    """True when at least one equipment alternative is fully covered."""
    return any(all(item in owned or item == BODYWEIGHT for item in alt) for alt in ex["equipment"])


NICE = {"pullup_bar": "pull-up bar", "medicine_ball": "medicine ball", "skierg": "SkiErg"}


def needs_text(ex: dict) -> str:
    alts = [" + ".join(NICE.get(i, i.replace("_", " ")) for i in a) for a in ex["equipment"]]
    return "no equipment" if alts == [BODYWEIGHT] else " or ".join(alts)


def public(ex: dict, owned: set[str] | None = None) -> dict:
    """The exercise as the API shows it, with its easier/harder neighbours and whether it is available."""
    out = {**ex, "needs": needs_text(ex), "easier": _neighbours(ex, -1), "harder": _neighbours(ex, 1)}
    if owned is not None:
        out["available"] = available(ex, owned)
    return out


def _neighbours(ex: dict, step: int) -> list[dict]:
    want = ex["level"] + step
    return [{"id": e["id"], "name": e["name"]} for e in library()["exercises"] if e["family"] == ex["family"] and e["pattern"] == ex["pattern"] and e["level"] == want and e["id"] != ex["id"]]


def _tokens(text: str) -> list[str]:
    return [t for t in re.split(r"[^a-z0-9]+", text.lower()) if t]


def search(q: str = "", pattern: str | None = None, owned: set[str] | None = None, level: int | None = None, tag: str | None = None, limit: int = 40) -> list[dict]:
    """Forgiving name search (every word must appear in the name, an alias or the muscles), optionally narrowed; best matches first."""
    words = _tokens(q)
    scored = []
    for e in library()["exercises"]:
        if pattern and e["pattern"] != pattern or tag and tag not in e["tags"] or level and e["level"] != level or owned is not None and not available(e, owned):
            continue
        hay = " ".join([e["name"], *e["aliases"], *e["muscles"]["primary"], e["pattern"], *e["tags"]]).lower()
        name = e["name"].lower()
        if not all(w in hay for w in words):
            continue
        rank = 0 if not words else (0 if name == q.lower().strip() else 1 if name.startswith(words[0]) else 2 if all(w in name for w in words) else 3)
        scored.append((rank, e["level"], e["name"], e))
    return [public(e, owned) for *_, e in sorted(scored, key=lambda s: s[:3])[:limit]]


# --------------------------------------------------------------------- prescriptions
GOAL_RX = {"general": (3, 10), "strength": (4, 5), "muscle": (3, 10), "endurance": (3, 15)}
# Cardio-ish distances and times when an exercise is added with no prescription.
DEFAULT_DISTANCE = {"run": 1000, "row": 500, "ski": 500, "walk": 1000, "carry": 40, "lunge": 40, "sled": 25, "burpee": 40}
DEFAULT_SECONDS = {"core": 30, "mobility": 40, "squat": 30, "plyometric": 30, "cardio": 600}


def default_rx(ex: dict, goal: str = "general", role: str = "main") -> dict:
    """A starting prescription for an exercise by its unit: sets/reps for strength work, seconds for holds, metres for carries."""
    sets, reps = GOAL_RX.get(goal, GOAL_RX["general"])
    unit = ex["unit"]
    if role in ("warmup", "mobility"):
        sets, reps = 2, 8
    if unit == "time":
        return {"sets": 3 if role != "warmup" else 2, "seconds": DEFAULT_SECONDS.get(ex["pattern"], 30)}
    if unit == "distance":
        key = ex.get("family") if ex.get("family") in DEFAULT_DISTANCE else ex["pattern"] if ex["pattern"] in DEFAULT_DISTANCE else "carry"
        return {"sets": 3 if ex["pattern"] != "cardio" and role not in ("warmup", "mobility") else 1, "distance_m": DEFAULT_DISTANCE.get(key, 40)}
    if unit == "calories":
        return {"sets": 1, "calories": 15}
    if ex["pattern"] == "olympic":
        sets, reps = 4, 5
    elif ex["pattern"] == "plyometric":
        sets, reps = 3, 6
    elif ex["pattern"] in ("core", "calves", "hips"):
        sets, reps = 3, 12 if goal != "endurance" else 15
    elif ex["pattern"] == "mobility":
        sets, reps = 1, 8
    return {"sets": sets, "reps": reps}


def default_rest(ex: dict, goal: str = "general") -> int:
    if ex["pattern"] in ("mobility", "drill", "cardio"):
        return 0
    if ex["pattern"] in ("core", "calves", "hips") or goal == "endurance":
        return 30
    return 150 if goal == "strength" and ex["level"] >= 3 and ex["pattern"] in ("squat", "hinge", "push", "pull") else 75


def step_for(ex: dict, goal: str = "general", role: str = "main") -> dict:
    rx = default_rx(ex, goal, role)
    return {"type": "exercise", "exercise": ex["id"], **rx, "rest_s": default_rest(ex, goal) if role != "warmup" else 0}


# --------------------------------------------------------------------- structure & validation
NUM = {"sets": (1, 20), "reps": (1, 500), "seconds": (1, 7200), "distance_m": (1, 100_000), "calories": (1, 500), "rest_s": (0, 900), "rounds": (1, 50)}


def _num(step: dict, key: str) -> int | None:
    v = step.get(key)
    if v is None:
        return None
    if isinstance(v, bool) or not isinstance(v, (int, float)) or not NUM[key][0] <= v <= NUM[key][1]:
        raise GymError(f"{key} must be a number from {NUM[key][0]} to {NUM[key][1]}")
    return int(v) if float(v).is_integer() else round(float(v), 1)


def normalize(steps: object, depth: int = 0, count: list[int] | None = None) -> list[dict]:
    """A clean copy of the steps, or GymError saying what is wrong. Unknown library ids are refused; own exercise names are allowed."""
    count = count if count is not None else [0]
    if not isinstance(steps, list) or not steps:
        raise GymError("A session needs at least one step")
    if depth >= MAX_DEPTH:
        raise GymError(f"Groups can nest up to {MAX_DEPTH} deep")
    out = []
    for raw in steps:
        count[0] += 1
        if count[0] > MAX_STEPS:
            raise GymError(f"At most {MAX_STEPS} steps in a session")
        if not isinstance(raw, dict):
            raise GymError("Each step must be an object")
        kind = raw.get("type", "exercise")
        if kind == "rest":
            sec = _num({"rest_s": raw.get("seconds", raw.get("rest_s"))}, "rest_s")
            if not sec:
                raise GymError("A rest step needs seconds")
            out.append({"type": "rest", "seconds": sec})
        elif kind == "group":
            rounds = _num(raw, "rounds") or 1
            inner = normalize(raw.get("steps"), depth + 1, count)
            title = str(raw.get("title") or "")[:60]
            out.append({"type": "group", "title": title, "rounds": rounds, "rest_s": _num(raw, "rest_s") or 0, "steps": inner})
        elif kind == "exercise":
            ex_id, name = raw.get("exercise"), str(raw.get("name") or "").strip()[:80]
            if ex_id is not None and exercise(str(ex_id)) is None:
                raise GymError(f"Unknown exercise: {ex_id}")
            if ex_id is None and not name:
                raise GymError("An exercise step needs an exercise id or a name")
            step: dict = {"type": "exercise"}
            if ex_id is not None:
                step["exercise"] = str(ex_id)
            else:
                step["name"] = name
            for key in ("sets", "reps", "seconds", "distance_m", "calories", "rest_s"):
                v = _num(raw, key)
                if v is not None:
                    step[key] = v
            load = raw.get("load")
            if load is not None and str(load).strip():
                step["load"] = str(load).strip()[:40]
            note = raw.get("note")
            if note is not None and str(note).strip():
                step["note"] = str(note).strip()[:200]
            if not any(k in step for k in ("reps", "seconds", "distance_m", "calories")):
                ex = exercise(step["exercise"]) if "exercise" in step else None
                step.update({k: v for k, v in (default_rx(ex) if ex else {"sets": 3, "reps": 10}).items() if k not in step})
            out.append(step)
        else:
            raise GymError("Step type must be exercise, rest or group")
    return out


def flatten(steps: list[dict]) -> list[dict]:
    """Exercise steps in order, groups expanded once (not per round)."""
    out: list[dict] = []
    for s in steps:
        if s["type"] == "group":
            out.extend(flatten(s["steps"]))
        elif s["type"] == "exercise":
            out.append(s)
    return out


def exercise_ids(steps: list[dict]) -> list[str]:
    return [s["exercise"] for s in flatten(steps) if "exercise" in s]


# --------------------------------------------------------------------- time
PACE_S_PER_M = {"run": 0.36, "row": 0.25, "ski": 0.26, "walk": 0.72, "carry": 1.4, "sled": 2.0, "lunge": 1.6, "burpee": 3.5}
CAL_PER_MIN = 14


def _step_seconds(step: dict) -> float:
    if step["type"] == "rest":
        return step["seconds"]
    if step["type"] == "group":
        inner = sum(_step_seconds(s) for s in step["steps"])
        return step["rounds"] * inner + max(0, step["rounds"] - 1) * step.get("rest_s", 0)
    sets = step.get("sets", 1)
    ex = exercise(step["exercise"]) if "exercise" in step else None
    if "reps" in step:
        work = step["reps"] * (2.5 if ex and ex["pattern"] in ("core", "calves", "hips") else 3.5)
    elif "seconds" in step:
        work = step["seconds"]
    elif "distance_m" in step:
        key = (ex or {}).get("family") if (ex or {}).get("family") in PACE_S_PER_M else (ex or {}).get("pattern", "carry")
        work = step["distance_m"] * PACE_S_PER_M.get(key, PACE_S_PER_M.get("carry", 1.4))
    elif "calories" in step:
        work = step["calories"] / CAL_PER_MIN * 60
    else:
        work = 30
    return sets * work + max(0, sets - 1) * step.get("rest_s", 0)


def estimate_minutes(steps: list[dict]) -> int:
    """A rough duration in whole minutes (at least 1): work from reps/time/distance plus the rests you wrote."""
    return max(1, round(sum(_step_seconds(s) for s in steps) / 60))


# --------------------------------------------------------------------- text for the existing parser
def describe(step: dict) -> str:
    ex = exercise(step["exercise"]) if "exercise" in step else None
    name = ex["name"] if ex else step.get("name", "Exercise")
    sets = step.get("sets", 1)
    if "reps" in step:
        amount = f"{sets} x {step['reps']}"
    elif "seconds" in step:
        amount = f"{sets} x {step['seconds']} s" if sets > 1 else f"{step['seconds']} s"
    elif "distance_m" in step:
        d = step["distance_m"]
        dist = f"{d / 1000:g} km" if d >= 1000 and d % 100 == 0 else f"{d} m"
        amount = f"{sets} x {dist}" if sets > 1 else dist
    elif "calories" in step:
        amount = f"{step['calories']} cal"
    else:
        amount = ""
    load = f" @ {step['load']}" if step.get("load") else ""
    return f"{name} {amount}{load}".strip()


def to_text(name: str, steps: list[dict]) -> str:
    """The session as class-style text the strength parser reads: a '#' title per block, exercise names only (so each is recognised)."""
    lines: list[str] = []

    def emit(block_name: str, items: list[dict]) -> None:
        names = []
        for s in items:
            if s["type"] == "exercise":
                ex = exercise(s["exercise"]) if "exercise" in s else None
                names.append(ex["name"] if ex else s.get("name", ""))
            elif s["type"] == "group":
                emit(s.get("title") or block_name, s["steps"])
        names = [n for n in names if n]
        if names:
            lines.append(f"# {block_name}")
            lines.extend(names)

    plain = [s for s in steps if s["type"] != "group"]
    # Top-level plain steps form one block named after the session; groups are their own blocks.
    if plain:
        emit(name or "Session", plain)
    for s in steps:
        if s["type"] == "group":
            emit(s.get("title") or "Round", s["steps"])
    return "\n".join(lines)


def outline(steps: list[dict], depth: int = 0) -> str:
    """One readable line per step (indented for groups): used in plan details and replies."""
    lines = []
    for s in steps:
        pad = "  " * depth
        if s["type"] == "group":
            rounds = f" x{s['rounds']}" if s["rounds"] > 1 else ""
            lines.append(f"{pad}{s.get('title') or 'Round'}{rounds}")
            lines.extend(outline(s["steps"], depth + 1).splitlines())
        elif s["type"] == "rest":
            lines.append(f"{pad}Rest {s['seconds']} s")
        else:
            lines.append(pad + describe(s))
    return "\n".join(lines)


# --------------------------------------------------------------------- swaps
def _muscles(ex: dict) -> set[str]:
    return set(ex["muscles"]["primary"])


def _overlap(a: dict, b: dict) -> float:
    """How alike two exercises are by the muscles they train: shared primary muscles, with a bonus when the main (first-listed) one matches."""
    ma, mb = _muscles(a), _muscles(b)
    base = len(ma & mb) / len(ma | mb) if ma | mb else 0.0
    lead = 0.5 if a["muscles"]["primary"] and b["muscles"]["primary"] and a["muscles"]["primary"][0] == b["muscles"]["primary"][0] else 0.0
    return base + lead


def _same_kind(cur: dict, e: dict) -> bool:
    """Conditioning work (thrusters, wall balls, swings) is only replaced by conditioning work, and a strength lift by a strength lift."""
    return ("conditioning" in cur["tags"]) == ("conditioning" in e["tags"])


def alternatives(ex_id: str, direction: str, owned: set[str], exclude: set[str] | None = None, limit: int = 5) -> list[dict]:
    """Ranked replacements: [{id, name, level, needs, reason}]. direction is easier, harder or different."""
    cur = exercise(ex_id)
    if cur is None:
        raise GymError("Unknown exercise")
    if direction not in ("easier", "harder", "different"):
        raise GymError("direction must be easier, harder or different")
    skip = (exclude or set()) | {ex_id}
    pool = [e for e in library()["exercises"] if e["id"] not in skip and available(e, owned)]
    scored: list[tuple[tuple, dict, str]] = []
    for e in pool:
        same_family = e["family"] == cur["family"] and e["pattern"] == cur["pattern"]
        shared = _overlap(cur, e)
        gap = e["level"] - cur["level"]
        if direction in ("easier", "harder"):
            sign = -1 if direction == "easier" else 1
            if gap * sign <= 0:
                continue
            if same_family:
                reason = f"Same movement, {'lighter' if direction == 'easier' else 'tougher'}"
                scored.append(((0, abs(gap), -shared), e, reason))
            elif e["pattern"] == cur["pattern"] and shared > 0 and _same_kind(cur, e):
                reason = f"Similar {cur['pattern']} work ({', '.join(sorted(_muscles(cur) & _muscles(e)))}), {direction}"
                scored.append(((1, abs(gap), -shared), e, reason))
        else:
            if same_family or abs(gap) > 1 or e["pattern"] != cur["pattern"] or shared == 0 or not _same_kind(cur, e):
                continue
            reason = f"A different {cur['pattern']} exercise for {', '.join(sorted(_muscles(cur) & _muscles(e)))}"
            scored.append(((0, -shared, abs(gap)), e, reason))
    if direction == "different" and len(scored) < limit and cur["pattern"] not in NO_CROSSOVER:  # widen: another pattern that trains the same muscles
        for e in pool:
            shared = _overlap(cur, e)
            if (e["pattern"] != cur["pattern"] and shared >= 0.9 and abs(e["level"] - cur["level"]) <= 1 and e["unit"] == cur["unit"]
                    and cur["pattern"] in LIFT_PATTERNS and e["pattern"] in LIFT_PATTERNS and _same_kind(cur, e)):
                scored.append(((1, -shared, abs(e["level"] - cur["level"])), e, f"Trains the same muscles ({', '.join(sorted(_muscles(cur) & _muscles(e)))}) with a different movement"))
    seen: set[str] = set()
    out = []
    for _, e, reason in sorted(scored, key=lambda s: (s[0], s[1]["name"])):
        if e["id"] in seen:
            continue
        seen.add(e["id"])
        out.append({"id": e["id"], "name": e["name"], "level": e["level"], "needs": needs_text(e), "reason": reason})
        if len(out) >= limit:
            break
    return out


def _replace_in_step(step: dict, new_id: str) -> dict:
    """The step with a different exercise. The prescription stays when the unit is the same, else the new exercise's defaults apply."""
    new = exercise(new_id)
    old = exercise(step["exercise"]) if "exercise" in step else None
    out = {"type": "exercise", "exercise": new_id}
    same_unit = old is not None and old["unit"] == new["unit"]
    if same_unit:
        out.update({k: step[k] for k in ("sets", "reps", "seconds", "distance_m", "calories", "rest_s", "note") if k in step})
        if new["pattern"] == old["pattern"] and step.get("load"):
            out["load"] = step["load"]
    else:
        out.update(default_rx(new))
        out["rest_s"] = step.get("rest_s", default_rest(new))
    return out


def swap_step(steps: list[dict], path: list[int], new_id: str, owned: set[str]) -> list[dict]:
    """A copy of the steps with the exercise at `path` (indexes through groups) replaced by `new_id`."""
    if exercise(new_id) is None:
        raise GymError("Unknown exercise")
    if not available(exercise(new_id), owned):
        raise GymError("That needs equipment you don't have for this session's setting")
    copy = json.loads(json.dumps(steps))
    level = copy
    try:
        for i in path[:-1]:
            level = level[i]["steps"]
        target = level[path[-1]]
    except (IndexError, KeyError, TypeError):
        raise GymError("No exercise at that position") from None
    if target.get("type") != "exercise":
        raise GymError("Only exercise steps can be swapped")
    level[path[-1]] = _replace_in_step(target, new_id)
    return copy


def step_at(steps: list[dict], path: list[int]) -> dict:
    level = steps
    try:
        for i in path[:-1]:
            level = level[i]["steps"]
        return level[path[-1]]
    except (IndexError, KeyError, TypeError):
        raise GymError("No step at that position") from None


def convert_setting(steps: list[dict], owned: set[str]) -> tuple[list[dict], list[dict]]:
    """Re-fit a session to the equipment you have. Returns (new steps, [{from, to, why}]) for every exercise that had to change.

    Each unavailable exercise becomes its closest available one: same family nearest level, else same pattern with overlapping muscles,
    else anything trained with the same muscles (cardio prefers other cardio). Exercises with no equipment need not change."""
    changes: list[dict] = []

    def best(ex: dict, taken: set[str]) -> dict | None:
        pool = [e for e in library()["exercises"] if available(e, owned) and e["id"] != ex["id"] and e["id"] not in taken]
        tiers: list[tuple[tuple, dict]] = []
        for e in pool:
            same_family = e["family"] == ex["family"] and e["pattern"] == ex["pattern"]
            shared = _overlap(ex, e)
            lvl = abs(e["level"] - ex["level"])
            if same_family:
                tiers.append(((0, lvl, 0), e))
            elif e["pattern"] == ex["pattern"] and shared > 0:
                tiers.append(((1, -shared, lvl), e))
            elif ex["pattern"] == "cardio" and e["pattern"] == "cardio":
                tiers.append(((1, 0, lvl), e))
            elif ex["pattern"] in ("cardio", "carry", "plyometric") and "conditioning" in e["tags"] and e["unit"] == ex["unit"]:
                tiers.append(((2, lvl, 0), e))
            elif shared >= 0.5 and e["pattern"] not in ("mobility", "drill"):
                tiers.append(((3, -shared, lvl), e))
        return min(tiers, key=lambda t: (t[0], t[1]["name"]))[1] if tiers else None

    def walk(items: list[dict]) -> list[dict]:
        taken = {s["exercise"] for s in flatten(items) if "exercise" in s}
        out = []
        for s in items:
            if s["type"] == "group":
                out.append({**s, "steps": walk(s["steps"])})
            elif s["type"] == "exercise" and "exercise" in s:
                ex = exercise(s["exercise"])
                if available(ex, owned):
                    out.append(s)
                    continue
                pick = best(ex, taken)
                if pick is None:
                    changes.append({"from": ex["name"], "to": None, "why": "Nothing available does a similar job, so it was left in"})
                    out.append(s)
                    continue
                taken.add(pick["id"])
                changes.append({"from": ex["name"], "to": pick["name"], "why": f"needs {needs_text(ex)}"})
                out.append(_replace_in_step(s, pick["id"]))
            else:
                out.append(s)
        return out

    return walk(json.loads(json.dumps(steps))), changes


# --------------------------------------------------------------------- templates
HYROX_STATIONS = [
    ("skierg", {"distance_m": 1000}), ("sled-push", {"distance_m": 50}), ("sled-pull", {"distance_m": 50}),
    ("burpee-broad-jump", {"distance_m": 80}), ("rowing-machine", {"distance_m": 1000}), ("farmers-carry", {"distance_m": 200}),
    ("sandbag-lunge", {"distance_m": 100}), ("wall-ball", {"reps": 100}),
]
# slot = (role, patterns to draw from (first with candidates wins), number)
TEMPLATES: dict[str, dict] = {
    "full_body": {"name": "Full body", "format": "straight", "blurb": "A squat, a hinge, a push, a pull and some core.",
                  "slots": [("main", ["squat"], 1), ("main", ["hinge"], 1), ("main", ["push"], 1), ("main", ["pull"], 1), ("accessory", ["lunge", "hips"], 1), ("core", ["core"], 2)]},
    "upper": {"name": "Upper body", "format": "straight", "blurb": "Pushing and pulling with arms and core.",
              "slots": [("main", ["push"], 2), ("main", ["pull"], 2), ("accessory", ["push", "pull"], 2), ("core", ["core"], 1)]},
    "lower": {"name": "Lower body", "format": "straight", "blurb": "Squat, hinge, single-leg work and calves.",
              "slots": [("main", ["squat"], 1), ("main", ["hinge"], 1), ("main", ["lunge"], 1), ("accessory", ["hips", "hinge"], 1), ("accessory", ["calves"], 1), ("core", ["core"], 1)]},
    "push": {"name": "Push", "format": "straight", "blurb": "Chest, shoulders and triceps.", "slots": [("main", ["push"], 5), ("core", ["core"], 1)]},
    "pull": {"name": "Pull", "format": "straight", "blurb": "Back and biceps, with rear shoulders.", "slots": [("main", ["pull"], 5), ("core", ["core"], 1)]},
    "legs_core": {"name": "Legs and core", "format": "straight", "blurb": "Lower body then trunk.",
                  "slots": [("main", ["squat"], 1), ("main", ["hinge"], 1), ("main", ["lunge"], 1), ("accessory", ["calves", "hips"], 1), ("core", ["core"], 3)]},
    "conditioning": {"name": "Conditioning circuit", "format": "circuit", "blurb": "Rounds of mixed work at a steady effort.",
                     "slots": [("circuit", ["plyometric"], 2), ("circuit", ["squat", "lunge"], 1), ("circuit", ["push"], 1), ("circuit", ["core"], 1), ("circuit", ["cardio"], 1)]},
    "run_lift": {"name": "Run + lift intervals", "format": "hybrid", "blurb": "Short runs alternating with a strength exercise, repeated.", "slots": []},
    "hyrox": {"name": "Hyrox race", "format": "hyrox", "blurb": "Eight rounds of a 1 km run then a station, in race order. Set station loads from the official rulebook for your division.", "slots": []},
    "hyrox_practice": {"name": "Hyrox practice", "format": "hyrox", "blurb": "The same eight stations at half distance with shorter runs, to rehearse the order.", "slots": []},
}
HOME_NAMES = {"full_body": "Home full body"}


def templates() -> list[dict]:
    return [{"id": k, "name": v["name"], "format": v["format"], "blurb": v["blurb"]} for k, v in TEMPLATES.items()]


def _pick(rng: random.Random, owned: set[str], patterns: list[str], lo: int, hi: int, taken_fam: set[str], taken_ids: set[str], tag_skip: tuple = ("warmup",)) -> dict | None:
    for pat in patterns:
        pool = [e for e in library()["exercises"] if e["pattern"] == pat and available(e, owned) and e["id"] not in taken_ids and e["family"] not in taken_fam
                and not (set(e["tags"]) & set(tag_skip) and pat not in ("mobility", "drill"))]
        if not pool and tag_skip:  # nothing else does this job with your equipment: allow the easy warm-up versions too
            pool = [e for e in library()["exercises"] if e["pattern"] == pat and available(e, owned) and e["id"] not in taken_ids and e["family"] not in taken_fam]
        near = [e for e in pool if lo <= e["level"] <= hi]
        # Prefer loaded options when you have the kit, then fall back to the nearest level.
        choices = near or sorted(pool, key=lambda e: abs(e["level"] - (lo + hi) / 2))[:3]
        if choices:
            return rng.choice(sorted(choices, key=lambda e: e["id"]))
    return None


def build(template_id: str, setting: str = "gym", owned: set[str] | None = None, minutes: int = 45, level: str = "intermediate", goal: str = "general", seed: int = 1) -> dict:
    """{name, format, setting, steps, notes}. Deterministic for the same inputs; minutes only trims or grows the number of accessories."""
    if template_id not in TEMPLATES:
        raise GymError("Unknown template")
    if setting not in SETTINGS:
        raise GymError("setting must be gym or home")
    if level not in LEVELS:
        raise GymError("level must be beginner, intermediate or advanced")
    if goal not in GOALS:
        raise GymError("goal must be general, strength, muscle or endurance")
    owned = owned if owned is not None else owned_set(setting, None)
    tpl = TEMPLATES[template_id]
    name = tpl["name"] if not (setting == "home" and template_id in HOME_NAMES) else HOME_NAMES[template_id]
    notes: list[str] = []
    if tpl["format"] == "hyrox":
        steps = _hyrox(template_id == "hyrox_practice")
        if setting == "home" or owned != owned_set("gym", None):
            steps, changes = convert_setting(steps, owned)
            notes += [f"{c['from']} → {c['to'] or 'kept'} ({c['why']})" for c in changes]
        notes.append("Station loads are blank on purpose: set them from the current official rulebook for your division.")
        hy = normalize(steps)
        notes.append(f"Hyrox is a fixed format: about {estimate_minutes(hy)} min at an easy pace whatever time you set, plus the warm-up.")
        return {"name": name + (" (home)" if setting == "home" else ""), "format": "hyrox", "setting": setting, "steps": hy, "notes": notes}
    rng = random.Random(f"{template_id}:{setting}:{level}:{goal}:{seed}")
    lo, hi = LEVELS[level]
    skip = ("warmup",) if template_id == "conditioning" else ("warmup", "conditioning", "hyrox")  # lifts are lifts: swings, thrusters and sled work belong elsewhere
    if template_id == "run_lift":
        return {"name": name, "format": "hybrid", "setting": setting, "steps": normalize(_run_lift(rng, owned, lo, hi, minutes, goal)), "notes": notes}
    taken_fam: set[str] = set()
    taken_ids: set[str] = set()
    warm: list[dict] = []
    for pat, count in (("mobility", 1), ("drill", 1)):
        for _ in range(count):
            e = _pick(rng, owned, [pat], 1, 2, taken_fam, taken_ids, tag_skip=())
            if e and ("warmup" in e["tags"] or pat == "mobility"):
                taken_ids.add(e["id"])
                taken_fam.add(e["family"])
                warm.append(step_for(e, goal, "warmup"))
    if template_id != "conditioning":
        warm.append(step_for(_pick(rng, owned, ["plyometric", "cardio"], 1, 1, taken_fam, taken_ids, tag_skip=()) or exercise("jumping-jack"), goal, "warmup"))
    main, extra = [], []
    for role, patterns, count in tpl["slots"]:
        for _ in range(count):
            e = _pick(rng, owned, patterns, lo, hi, taken_fam, taken_ids, tag_skip=skip)
            if e is None:
                notes.append(f"Nothing available for {'/'.join(patterns)} with your equipment, so it was left out")
                continue
            taken_ids.add(e["id"])
            taken_fam.add(e["family"])
            (extra if role in ("accessory", "core") else main).append((role, e))
    if any(e["pattern"] == "pull" and "warmup" in e["tags"] for _, e in main + extra):
        notes.append("Pulling with no equipment is limited to light shoulder-blade work. Tick a loaded backpack, band or pull-up bar in your home equipment to add rows and pull-ups.")
    warm_group = [{"type": "group", "title": "Warm-up", "rounds": 1, "steps": warm}] if warm else []
    if tpl["format"] == "circuit":
        inner = [step_for(e, "endurance", "circuit") | {"rest_s": 0} for _, e in main]
        for s_ in inner:
            s_["sets"] = 1
            ex = exercise(s_["exercise"])
            if "reps" in s_:
                s_["reps"] = 12 if ex["pattern"] != "plyometric" else 8
            if "distance_m" in s_ and ex["pattern"] == "cardio":
                s_["distance_m"] = 200  # a short effort inside a round, not a 1 km run
        per_round = sum(_step_seconds({**s_, "type": "exercise"}) for s_ in inner) + 90
        warm_s = sum(_step_seconds(s_) for s_ in warm_group)
        rounds = min(8, max(2, round((minutes * 60 - warm_s) / max(per_round, 1))))
        steps = warm_group + [{"type": "group", "title": "Circuit", "rounds": rounds, "rest_s": 90, "steps": inner}]
    else:
        main_steps = [step_for(e, goal, role) for role, e in main]
        acc_steps = [step_for(e, "muscle" if role == "accessory" and goal == "strength" else goal, role) for role, e in extra]
        main_steps, acc_steps = _fit(warm_group, main_steps, acc_steps, minutes, goal, rng, owned, taken_fam, taken_ids, lo, hi, skip)
        steps = warm_group + ([{"type": "group", "title": "Main", "rounds": 1, "steps": main_steps}] if main_steps else [])
        if acc_steps:
            steps.append({"type": "group", "title": "Accessory and core", "rounds": 1, "steps": acc_steps})
    if setting == "home":
        notes.append("Home session: only bodyweight and the equipment you listed. Make it harder with slower reps, pauses or a harder version.")
    out_steps = normalize(steps)
    est = estimate_minutes(out_steps)
    if abs(est - minutes) > max(5, minutes * 0.15):
        notes.append(f"This comes to about {est} min (you asked for {minutes}): it can't be stretched or shrunk further without padding or cutting what the template needs.")
    return {"name": name + (" (home)" if setting == "home" and template_id not in HOME_NAMES else ""), "format": tpl["format"], "setting": setting,
            "steps": out_steps, "notes": notes}


ACCESSORY_ORDER = ["lunge", "hips", "push", "pull", "core", "calves"]


def _fit(warm_group, main_steps, acc_steps, minutes, goal, rng, owned, taken_fam, taken_ids, lo, hi, skip):
    """Grow or trim a straight session toward the minutes asked (within about 10%): more sets on the main lifts and another accessory when
    short; fewer sets and accessories when long. Deterministic for the same rng state."""
    def groups():
        return warm_group + [{"type": "group", "title": "m", "rounds": 1, "steps": main_steps}] + ([{"type": "group", "title": "a", "rounds": 1, "steps": acc_steps}] if acc_steps else [])

    cycle = 0
    for _ in range(30):
        est = estimate_minutes(groups()) if main_steps else 0
        if not main_steps or minutes * 0.9 <= est <= minutes * 1.1:
            break
        if est < minutes * 0.9:
            cycle += 1
            growable = [s for s in main_steps if "reps" in s and s.get("sets", 1) < 5]
            if len(acc_steps) < 5 and (cycle % 2 == 0 or not growable):
                e = _pick(rng, owned, [ACCESSORY_ORDER[(len(acc_steps) + cycle) % len(ACCESSORY_ORDER)]], lo, hi, taken_fam, taken_ids, tag_skip=skip)
                if e:
                    taken_ids.add(e["id"])
                    taken_fam.add(e["family"])
                    acc_steps.append(step_for(e, "muscle" if goal == "strength" else goal, "accessory"))
                    continue
            if growable:
                min(growable, key=lambda s: s.get("sets", 1))["sets"] += 1
                continue
            break
        reducible = [s for s in main_steps if s.get("sets", 1) > 2]
        if reducible:
            max(reducible, key=lambda s: s.get("sets", 1))["sets"] -= 1
        elif len(acc_steps) > 1:
            acc_steps.pop()
        else:
            break
    return main_steps, acc_steps


def _hyrox(practice: bool) -> list[dict]:
    scale = 0.5 if practice else 1
    steps: list[dict] = [{"type": "group", "title": "Warm-up", "rounds": 1, "steps": [
        {"type": "exercise", "exercise": "worlds-greatest-stretch", "sets": 1, "reps": 5},
        {"type": "exercise", "exercise": "a-skip", "sets": 2, "distance_m": 30},
        {"type": "exercise", "exercise": "run", "sets": 1, "distance_m": 400, "note": "easy"}]}]
    for i, (ex_id, amount) in enumerate(HYROX_STATIONS, 1):
        station = {"type": "exercise", "exercise": ex_id}
        station.update({k: max(1, round(v * scale)) for k, v in amount.items()})
        station["sets"] = 1
        run = {"type": "exercise", "exercise": "run", "sets": 1, "distance_m": 500 if practice else 1000}
        title = f"{i} · {exercise(ex_id)['name']}"
        steps.append({"type": "group", "title": title, "rounds": 1, "steps": [run, station]})
    return steps


def _run_lift(rng: random.Random, owned: set[str], lo: int, hi: int, minutes: int, goal: str) -> list[dict]:
    rounds = min(8, max(3, round((minutes - 5) / 5.4)))  # about 5.4 min per round: an 800 m run and a set of a lift
    taken_fam: set[str] = set()
    taken_ids: set[str] = set()
    lifts = []
    for pats in (["squat", "lunge"], ["hinge"], ["push"], ["pull"]):
        e = _pick(rng, owned, pats, lo, hi, taken_fam, taken_ids, tag_skip=("warmup", "conditioning", "hyrox"))
        if e:
            taken_ids.add(e["id"])
            taken_fam.add(e["family"])
            lifts.append(e)
    steps: list[dict] = []
    for i in range(rounds):
        e = lifts[i % len(lifts)]
        lift = step_for(e, "muscle" if goal == "general" else goal)
        lift["sets"] = 1
        lift["rest_s"] = 0
        steps.append({"type": "group", "title": f"Round {i + 1}", "rounds": 1, "steps": [{"type": "exercise", "exercise": "run", "sets": 1, "distance_m": 800}, lift]})
    return steps


# --------------------------------------------------------------------- what next time?
def parse_kg(load: object) -> float | None:
    """A number of kilograms from text like '40', '40 kg', '42.5kg'; None for bodyweight, bands or anything else."""
    m = re.fullmatch(r"\s*(\d+(?:[.,]\d+)?)\s*(kg|kgs)?\s*", str(load or "").lower())
    return float(m.group(1).replace(",", ".")) if m else None


def progression_hint(ex_id: str | None, sets: list[dict]) -> dict | None:
    """A small, transparent suggestion for next time from how the last session went (double progression, as in ACSM's progression models:
    first earn the reps at a load, then raise the load a little). It is a suggestion, never a prescription; it uses only logged sets that
    carry the reps you were aiming for. Returns {kind, text, load?} or None when there is nothing to go on."""
    done = [s for s in sets if s.get("done")]
    aimed = [s for s in done if s.get("target_reps") and s.get("reps") is not None]
    if not aimed:
        return None
    hit = all(s["reps"] >= s["target_reps"] for s in aimed) and len(aimed) == len(done)
    ex = exercise(ex_id) if ex_id else None
    kg = parse_kg(aimed[-1].get("load"))
    if not hit:
        short = next(s for s in aimed if s["reps"] < s["target_reps"])
        return {"kind": "repeat", "text": f"Last time one set stopped at {short['reps']} of {short['target_reps']} reps. Repeat the same load and aim to hit every rep before going up."}
    if kg is not None and kg > 0:
        lower = bool(ex and ex["pattern"] in ("squat", "hinge", "lunge"))
        step = max(1.0, round(kg * (0.05 if lower else 0.025) * 2) / 2)
        nxt = kg + step
        label = f"{nxt:g} kg"
        return {"kind": "increase_load", "load": label, "text": f"You hit every rep at {kg:g} kg last time. If it felt solid, try {label} (a small step of {step:g} kg); otherwise repeat."}
    harder = _neighbours(ex, 1) if ex else []
    extra = f", or try {harder[0]['name']}" if harder else ""
    return {"kind": "increase_reps", "text": f"You hit every rep last time. Add a rep or two per set{extra}."}


# --------------------------------------------------------------------- from a screenshot or pasted text
_RX_SETS_REPS = re.compile(r"\b(\d{1,2})\s*[x×]\s*(\d{1,3})\b(?!\s*(?:m\b|km\b|s\b|sec|min))", re.I)
_RX_SETS_SECS = re.compile(r"\b(\d{1,2})\s*[x×]\s*(\d{1,4})\s*(?:s|sec|secs|seconds)\b", re.I)
_RX_SECS = re.compile(r"\b(\d{1,4})\s*(?:s|sec|secs|seconds)\b", re.I)
_RX_MINS = re.compile(r"\b(\d{1,3})\s*(?:min|mins|minutes)\b", re.I)
_RX_DIST = re.compile(r"\b(\d+(?:[.,]\d+)?)\s*(km|m)\b", re.I)
_RX_CAL = re.compile(r"\b(\d{1,3})\s*cal(?:ories)?\b", re.I)
_RX_REPS = re.compile(r"\b(\d{1,3})\s*reps?\b", re.I)
_RX_LEAD = re.compile(r"^\s*(\d{1,3})\s+(?=[A-Za-z])")
_RX_X_REPS = re.compile(r"(?<![\d\w])[x×]\s*(\d{1,3})\b", re.I)  # "squats x10"
_RX_TRAIL = re.compile(r"(?<=[A-Za-z\)])\s+(\d{1,3})\s*$")  # "Burpees 20"
_RX_LOAD = re.compile(r"\b(\d+(?:[.,]\d+)?)\s*(kg|kgs|lb|lbs)\b", re.I)
_RX_ROUNDS = re.compile(r"\b(\d{1,2})\s*(?:rounds?|sets?|rds?)\b|\b[x×]\s*(\d{1,2})\b", re.I)


def _lib_index() -> dict[str, dict]:
    from cadence_app.analytics import exercises as X

    out: dict[str, dict] = {}
    for e in library()["exercises"]:
        for alias in [e["name"], *e["aliases"]]:
            for key in X._keys(alias):
                out.setdefault(key, e)
    return out


def _prescription(line: str) -> tuple[str, dict]:
    """(the line without its numbers, a step prescription found in it). Understands 3x10, 4 x 30 s, 45 sec, 2 min, 400 m, 1 km, 12 reps, 20 cal, 20 kg."""
    rest, rx = line, {}
    load = _RX_LOAD.search(rest)
    if load:
        rx["load"] = f"{load.group(1).replace(',', '.')} {'kg' if load.group(2).lower().startswith('kg') else 'lb'}"
        rest = rest.replace(load.group(0), " ")
    for pattern, kind in ((_RX_SETS_SECS, "sets_secs"), (_RX_SETS_REPS, "sets_reps"), (_RX_DIST, "dist"), (_RX_MINS, "mins"), (_RX_SECS, "secs"), (_RX_CAL, "cal"), (_RX_REPS, "reps"), (_RX_X_REPS, "reps"), (_RX_LEAD, "lead"), (_RX_TRAIL, "reps")):
        m = pattern.search(rest)
        if not m or any(k in rx for k in ("reps", "seconds", "distance_m", "calories")) and kind not in ("sets_reps", "sets_secs"):
            continue
        if kind == "sets_secs":
            rx.update(sets=int(m.group(1)), seconds=int(m.group(2)))
        elif kind == "sets_reps":
            rx.update(sets=int(m.group(1)), reps=int(m.group(2)))
        elif kind == "dist":
            n = float(m.group(1).replace(",", "."))
            rx["distance_m"] = int(round(n * (1000 if m.group(2).lower() == "km" else 1)))
        elif kind == "mins":
            rx["seconds"] = int(m.group(1)) * 60
        elif kind == "secs":
            rx["seconds"] = int(m.group(1))
        elif kind == "cal":
            rx["calories"] = int(m.group(1))
        else:
            rx["reps"] = int(m.group(1))
        rest = rest.replace(m.group(0), " ", 1) if kind != "lead" else rest[m.end():]
    name = re.sub(r"\s+", " ", re.sub(r"[@:–—\-|,;()]+\s*$", "", re.sub(r"[()|@]", " ", rest))).strip(" -–—:,.")
    return name, rx


GENERIC_WITH_AMOUNT = {"row": "rowing-machine", "rowing": "rowing-machine", "ski": "skierg", "skierg": "skierg", "bike": "assault-bike", "run": "run", "jog": "run", "running": "run"}


def _candidates(name: str) -> list[str]:
    """Keys to look a name up by: as written, singular, and without spaces ("push-ups" -> push up, pushup)."""
    from cadence_app.analytics import exercises as X

    out: list[str] = []
    for k in X._keys(name):
        for v in (k, k[:-1] if k.endswith("s") else k, k.replace(" ", ""), k.replace(" ", "")[:-1] if k.endswith("s") else k.replace(" ", "")):
            if v not in out:
                out.append(v)
    return out


def import_text(text: str) -> dict:
    """A draft gym session from pasted or screenshot text (class listings, a coach's plan): {name, format, steps, unmatched, matched, total}.

    Reuses the class parser to find blocks and exercise lines, reads a prescription from each line when there is one, and matches the name
    to the library (names and aliases) so the exercise gets its how-to and can be swapped. A line that isn't in the library is kept as your
    own exercise by name rather than dropped. Nothing is saved; the draft is meant to be reviewed."""
    from cadence_app.analytics import exercises as X

    blocks = X.parse(text)
    index = _lib_index()
    steps: list[dict] = []
    unmatched: list[str] = []
    matched = total = 0
    for b in blocks:
        inner: list[dict] = []
        for ex in b["exercises"]:
            name, rx = _prescription(ex["name"])
            if not name:
                continue
            total += 1
            lib = next((index[k] for k in _candidates(name) if k in index), None)
            if lib is None and X._norm(name) in GENERIC_WITH_AMOUNT and any(k in rx for k in ("distance_m", "calories", "seconds")):
                lib = exercise(GENERIC_WITH_AMOUNT[X._norm(name)])
            step: dict = {"type": "exercise"}
            if lib is not None:
                matched += 1
                step["exercise"] = lib["id"]
                base = default_rx(lib)
            else:
                unmatched.append(name)
                step["name"] = name[:80]
                base = {"sets": 3, "reps": 10}
            if any(k in rx for k in ("reps", "seconds", "distance_m", "calories")):
                step.update({k: v for k, v in rx.items() if k in ("sets", "reps", "seconds", "distance_m", "calories", "load")})
                step.setdefault("sets", 1 if lib is not None and lib["pattern"] in ("mobility", "drill", "cardio") or "reps" not in rx else 3)
            else:
                step.update(base)
                if rx.get("load"):
                    step["load"] = rx["load"]
            inner.append(step)
        if not inner:
            continue
        title = re.sub(r"\s+", " ", b.get("name") or "Block").strip()[:60]
        rounds_m = _RX_ROUNDS.search(title)
        rounds = int(next(g for g in rounds_m.groups() if g)) if rounds_m else 1
        steps.append({"type": "group", "title": title, "rounds": max(1, min(rounds, 50)), "steps": inner})
    used = {X._norm(ex["name"]) for b in blocks for ex in b["exercises"]} | {X._norm(b.get("name") or "") for b in blocks}
    ignored = []
    for ln in text.splitlines():
        clean = re.sub(r"\s+", " ", ln).strip(" •-–—*\t")
        if clean and not clean.startswith("#") and X._norm(clean) not in used and clean not in ignored and len(clean) <= 80:
            ignored.append(clean)
    if not steps:
        raise GymError("Nothing that looks like an exercise was found. Put one exercise per line, with block titles on their own lines.")
    return {"name": "Imported session", "format": "custom", "steps": normalize(steps), "unmatched": unmatched, "ignored": ignored[:15], "matched": matched, "total": total}
