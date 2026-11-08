"""Which foods to put first when you log: frecency, usual combinations for a meal, the meal slot for a time, portion habits.

Pure functions over plain records (no database, no clock). Loading lives in `food_quick.py`, wording in `notes.py`.
Everything is computed from your own log; nothing here judges a food or a day.

Method (docs/food-logging-design.md section 2b)
- Frecency (a recency-weighted count, the idea behind browser "frecent" ranking): each past log of a dish adds
  0.5^(age_days / 14), a 14-day half-life, times (1 + 0.5 if it was the same meal slot + 0.3 if it was the same weekday).
  The scores are divided by the largest one so they run 0..1. A dish logged only once is capped at 0.2, so one
  accident does not lead the list.
- Usual combinations: for one meal slot, the set of dishes logged on each of the last 60 days; days whose sets overlap
  (Jaccard similarity >= 0.6 with the first day of a cluster, taking the most recent day first) form a cluster. A
  cluster needs >= 3 days to count. Clusters rank by the recency-weighted number of days (same half-life) plus 0.3 when
  one of its days fell on the same weekday. Typical servings are the median over its days.
- Portion habit: the amount last logged is remembered; the same amount three times running marks it as a habit.
"""

from __future__ import annotations

from datetime import date
from statistics import median

HALF_LIFE_DAYS = 14.0
SAME_MEAL_BOOST = 0.5
SAME_WEEKDAY_BOOST = 0.3
SINGLE_LOG_CAP = 0.2
USUAL_WINDOW_DAYS = 60
USUAL_JACCARD = 0.6
USUAL_MIN_DAYS = 3
USUAL_WEEKDAY_BONUS = 0.3
HABIT_STREAK = 3
MEAL_DEFAULT_TIMES = {"breakfast": (8, 0), "lunch": (13, 0), "snack": (16, 30), "dinner": (20, 0)}


def decay(age_days: float) -> float:
    return 0.5 ** (max(age_days, 0.0) / HALF_LIFE_DAYS)


def frecency(logs: list[dict], today: date, meal: str | None = None, weekday: int | None = None) -> dict[int, float]:
    """`logs` = [{dish_id, day, meal}]. Returns dish_id -> 0..1. Weekday defaults to today's."""
    weekday = today.weekday() if weekday is None else weekday
    raw: dict[int, float] = {}
    count: dict[int, int] = {}
    for r in logs:
        if r.get("dish_id") is None or r["day"] > today:
            continue
        w = decay((today - r["day"]).days) * (1 + SAME_MEAL_BOOST * (meal is not None and r["meal"] == meal)
                                              + SAME_WEEKDAY_BOOST * (r["day"].weekday() == weekday))
        raw[r["dish_id"]] = raw.get(r["dish_id"], 0.0) + w
        count[r["dish_id"]] = count.get(r["dish_id"], 0) + 1
    top = max(raw.values(), default=0.0)
    if top <= 0:
        return {}
    return {d: (min(v / top, SINGLE_LOG_CAP) if count[d] < 2 else v / top) for d, v in raw.items()}


def meal_guess(minute_of_day: int) -> str:
    """Before 11:00 breakfast, to 15:30 lunch, to 18:30 snack, then dinner."""
    if minute_of_day < 11 * 60:
        return "breakfast"
    if minute_of_day < 15 * 60 + 30:
        return "lunch"
    if minute_of_day < 18 * 60 + 30:
        return "snack"
    return "dinner"


def jaccard(a: set, b: set) -> float:
    return len(a & b) / len(a | b) if a or b else 0.0


def usual_combos(logs: list[dict], today: date, meal: str, weekday: int | None = None) -> list[dict]:
    """`logs` = [{dish_id, day, meal, servings}]. Returns clusters best first:
    {dish_ids, servings{dish_id: median}, n_days, score, last_day}."""
    weekday = today.weekday() if weekday is None else weekday
    per_day: dict[date, dict[int, list[float]]] = {}
    for r in logs:
        if r.get("dish_id") is None or r["meal"] != meal or not 0 <= (today - r["day"]).days <= USUAL_WINDOW_DAYS:
            continue
        per_day.setdefault(r["day"], {}).setdefault(r["dish_id"], []).append(r["servings"])
    clusters: list[dict] = []
    for day in sorted(per_day, reverse=True):
        ids = set(per_day[day])
        for c in clusters:
            if jaccard(c["rep"], ids) >= USUAL_JACCARD:
                c["days"].append(day)
                break
        else:
            clusters.append({"rep": ids, "days": [day]})
    out = []
    for c in clusters:
        if len(c["days"]) < USUAL_MIN_DAYS:
            continue
        n = len(c["days"])
        seen: dict[int, list[float]] = {}
        for d in c["days"]:
            for dish_id, servings in per_day[d].items():
                seen.setdefault(dish_id, []).append(sum(servings))
        keep = {dish_id: vals for dish_id, vals in seen.items() if len(vals) * 2 >= n}  # in at least half of the days
        score = sum(decay((today - d).days) for d in c["days"]) + (USUAL_WEEKDAY_BONUS if any(d.weekday() == weekday for d in c["days"]) else 0.0)
        out.append({"dish_ids": sorted(keep, key=lambda i: (-len(keep[i]), i)), "servings": {i: round(median(v), 2) for i, v in keep.items()},
                    "n_days": n, "score": round(score, 4), "last_day": c["days"][0]})
    out.sort(key=lambda c: (-c["score"], -c["n_days"], c["dish_ids"]))
    return out


def next_memory(prev: dict | None, servings: float, unit: str | None, grams: float | None) -> dict:
    """What to remember after a log: the amount, how many logs, and the run of identical amounts."""
    same = prev is not None and abs(prev["servings"] - servings) < 1e-6
    return {"servings": servings, "unit": unit, "grams": grams, "n": (prev["n"] if prev else 0) + 1, "streak": prev["streak"] + 1 if same else 1}


def is_habit(mem: dict | None) -> bool:
    return bool(mem) and mem["streak"] >= HABIT_STREAK
