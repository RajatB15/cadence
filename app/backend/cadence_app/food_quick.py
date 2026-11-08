"""Loading and assembling the quick-logging helpers: one-tap chips, portion memory, barcode lookup in your own products, suggestions.

The ranking and scoring are pure and live in `analytics/foodrank.py` and `analytics/foodsuggest.py`; the sentences in
`analytics/notes.py`. This module only reads your log and dishes, calls them and shapes the JSON. Everything comes from
your own history: no network call, no external food database. Removed entries never count (`foodlog.active_entries`).
"""

from __future__ import annotations

import json
from datetime import date, timedelta

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from cadence_app import foodlog, nutrients
from cadence_app.analytics import foodrank, foodsuggest, notes
from cadence_app.models import FoodDish, FoodEntry, FoodMeal, FoodMealItem, FoodPortionMemory

MAX_CHIPS = 6
HISTORY_DAYS = 60


def memory(session: Session) -> dict[int, dict]:
    return {m.dish_id: {"servings": m.servings, "unit": m.unit, "grams": m.grams, "habitual": foodrank.is_habit({"streak": m.streak})}
            for m in session.scalars(select(FoodPortionMemory))}


def reset_memory(session: Session) -> int:
    n = session.execute(delete(FoodPortionMemory)).rowcount
    session.commit()
    return n


def history(session: Session, until: date, days: int = HISTORY_DAYS) -> list[dict]:
    """Active entries of the last `days` days before and including `until`."""
    rows = session.scalars(foodlog.active_entries().where(FoodEntry.day >= until - timedelta(days=days), FoodEntry.day <= until))
    return [{"dish_id": e.dish_id, "day": e.day, "meal": e.meal, "servings": e.servings, "name": e.name} for e in rows]


def _range(items: list[dict]) -> dict:
    return {"value": round(sum(i["kcal"] for i in items)), "low": round(sum(i["kcal"] * (1 - i["spread"] / 100) for i in items)),
            "high": round(sum(i["kcal"] * (1 + i["spread"] / 100) for i in items))}


def _dish_item(d: FoodDish, servings: float, mem: dict | None) -> dict | None:
    """A dish at an amount, with what it adds up to. None when the dish can't be logged any more."""
    if not d.active:
        return None
    try:
        p = foodlog._portion(d, servings, None)  # pylint: disable=protected-access
    except foodlog.FoodError:
        return None
    unit = (mem or {}).get("unit")
    if not unit or unit == "g":
        unit = foodlog._unit_label(d, None, False)  # pylint: disable=protected-access
    return {"dish_id": d.id, "name": d.name, "servings": round(servings, 2), "unit": unit, "kcal": round(p["kcal"]),
            "protein_g": None if p["protein_g"] is None else round(p["protein_g"], 1), "spread": d.spread_pct, "micros": p["micros"]}


def _item_for(session: Session, dish_id: int, servings: float, mem: dict | None) -> dict | None:
    d = session.get(FoodDish, dish_id)
    return _dish_item(d, servings, mem) if d is not None else None


def _public(items: list[dict]) -> list[dict]:
    return [{k: v for k, v in i.items() if k not in ("spread", "micros")} for i in items]


def _chip(kind: str, cid: str, label: str, items: list[dict], **extra) -> dict:
    return {"kind": kind, "id": cid, "label": label, "items": _public(items), "kcal": _range(items), **extra}


def _entry_items(session: Session, rows: list[FoodEntry], mem: dict[int, dict]) -> list[dict]:
    out = []
    for e in rows:
        d = session.get(FoodDish, e.dish_id) if e.dish_id else None
        unit = foodlog._unit_label(d, (mem.get(e.dish_id) or {}).get("unit"), False) if d else "serving"  # pylint: disable=protected-access
        out.append({"dish_id": e.dish_id, "name": e.name, "servings": round(e.servings, 2), "unit": unit, "kcal": round(e.kcal),
                    "protein_g": None if e.protein_g is None else round(e.protein_g, 1), "spread": e.spread_pct})
    return out


def _meal_items(session: Session, m: FoodMeal) -> list[dict]:
    out = []
    for it in session.scalars(select(FoodMealItem).where(FoodMealItem.meal_id == m.id).order_by(FoodMealItem.position, FoodMealItem.id)):
        d = session.get(FoodDish, it.dish_id) if it.dish_id else None
        v = foodlog._item_values(it, d)  # pylint: disable=protected-access
        out.append({"dish_id": it.dish_id, "name": it.name, "servings": round(v["servings"], 2), "unit": foodlog._unit_label(d, None, False) if d else "serving",  # pylint: disable=protected-access
                    "kcal": round(v["kcal"]), "protein_g": None if v["protein_g"] is None else round(v["protein_g"], 1),
                    "spread": it.spread_pct if d is None else d.spread_pct, "micros": v["micros"]})
    return out


def _names(items: list[dict]) -> str:
    return " + ".join(i["name"] for i in items[:3]) + (f" + {len(items) - 3} more" if len(items) > 3 else "")


def quick(session: Session, day: date, meal: str, today: date) -> dict:
    """One-tap chips for a meal: your usual combinations, yesterday's same meal, saved meals, pinned dishes, the last entry."""
    mem = memory(session)
    hist = history(session, min(day, today))
    chips: list[dict] = []
    for k, u in enumerate(foodrank.usual_combos(hist, day, meal)[:2]):
        items = []
        for dish_id in u["dish_ids"]:
            if it := _item_for(session, dish_id, u["servings"][dish_id], mem.get(dish_id)):
                items.append(it)
        if items:
            chips.append(_chip("usual", f"u:{meal}:{k}", f"Usual {meal}", items, n_days=u["n_days"]))
    prev = list(session.scalars(foodlog.active_entries().where(FoodEntry.day == day - timedelta(days=1), FoodEntry.meal == meal).order_by(FoodEntry.id)))
    if prev:
        chips.append(_chip("yesterday", f"y:{meal}", f"Same as yesterday's {meal}", _entry_items(session, prev, mem)))
    saved = foodlog.meals(session)
    saved.sort(key=lambda m: not m["pinned"])  # stable: pinned first, then most recently used (meals() order)
    for m in saved[:2]:
        row = session.get(FoodMeal, m["id"])
        items = _meal_items(session, row)
        if items:
            chips.append(_chip("saved", f"m:{m['id']}", m["name"], items))
    pinned_dishes = list(session.scalars(select(FoodDish).where(FoodDish.pinned.is_(True), FoodDish.active.is_(True)).order_by(FoodDish.name)))
    for d in pinned_dishes[:2]:
        it = _dish_item(d, (mem.get(d.id) or {}).get("servings", 1.0), mem.get(d.id))
        if it:
            chips.append(_chip("pinned", f"p:{d.id}", d.name, [it]))
    last = session.scalars(foodlog.active_entries().order_by(FoodEntry.id.desc()).limit(1)).first()
    if last is not None:
        chips.append(_chip("last", f"l:{last.id}", f"Repeat {last.name}", _entry_items(session, [last], mem)))
    return {"chips": chips[:MAX_CHIPS], "memory": {str(k): v for k, v in mem.items()},
            "pinned": [d.id for d in pinned_dishes], "pinned_meals": [m["id"] for m in saved if m["pinned"]]}


def barcode(session: Session, code: str) -> dict:
    """Your own saved product with this code, or not found. No online lookup exists in Cadence."""
    code = foodlog.clean_barcode(code)
    if code is None:
        raise foodlog.FoodError("A barcode is 6 to 14 digits")
    d = session.scalar(select(FoodDish).where(FoodDish.barcode == code))
    if d is None:
        return {"found": False, "online_lookup": "off"}
    m = memory(session).get(d.id)
    return {"found": True, "dish": foodlog.dish_dict(d), "portion": m}


# ---- what to eat now ----


def _micro_sum(items: list[dict]) -> dict[str, float] | None:
    total: dict[str, float] = {}
    for i in items:
        for k, v in (i.get("micros") or {}).items():
            total[k] = total.get(k, 0.0) + v
    return {k: round(v, 2) for k, v in total.items()} or None


def _candidate(label: str, source: str, items: list[dict], habit: float, times: int) -> dict | None:
    if not items:
        return None
    r = _range(items)
    known = [i["protein_g"] for i in items]
    return {"label": label, "source": source, "items": _public(items), "kcal": r["value"], "kcal_low": r["low"], "kcal_high": r["high"],
            "protein_g": None if any(p is None for p in known) else round(sum(known), 1), "micros": _micro_sum(items), "habit": habit, "times": times}


def suggest(session: Session, day: date, meal: str, today: date, view: dict, plan: dict | None) -> dict:
    """The ranked picks for a meal, from your own history against what is left of the day."""
    ref = min(day, today)
    hist = history(session, ref)
    n_history = session.scalar(select(func.count()).select_from(FoodEntry).where(
        FoodEntry.deleted_at.is_(None), FoodEntry.day >= ref - timedelta(days=90), FoodEntry.day <= ref)) or 0
    mem = memory(session)
    fre = foodrank.frecency(hist, ref, meal, day.weekday())
    count30 = {}
    for r in hist:
        if r["dish_id"] is not None and (ref - r["day"]).days <= 30:
            count30[r["dish_id"]] = count30.get(r["dish_id"], 0) + 1

    def habit(items: list[dict]) -> float:
        ids = [i["dish_id"] for i in items if i.get("dish_id") is not None]
        return sum(fre.get(i, 0.0) for i in ids) / len(ids) if ids else 0.0

    cands: list[dict] = []
    for u in foodrank.usual_combos(hist, ref, meal, day.weekday()):
        items = [it for it in (_item_for(session, i, u["servings"][i], mem.get(i)) for i in u["dish_ids"]) if it]
        if c := _candidate(_names(items) if items else "", "usual", items, habit(items), u["n_days"]):
            cands.append(c)
    for m in session.scalars(select(FoodMeal)):
        items = _meal_items(session, m)
        if c := _candidate(m.name, "saved", items, habit(items), 0):
            cands.append(c)
    eaten_now = {e["dish_id"] for e in view["entries"] if e["meal"] == meal and e["dish_id"] is not None}
    slot_ids = {r["dish_id"] for r in hist if r["meal"] == meal and r["dish_id"] is not None}
    pinned = set(session.scalars(select(FoodDish.id).where(FoodDish.pinned.is_(True))))
    for dish_id in sorted((slot_ids | pinned) - eaten_now):
        it = _item_for(session, dish_id, (mem.get(dish_id) or {}).get("servings", 1.0), mem.get(dish_id))
        if it and (c := _candidate(it["name"], "dish", [it], fre.get(dish_id, 0.0), count30.get(dish_id, 0))):
            cands.append(c)

    summary = view["summary"]
    targets = (plan or {}).get("targets")
    remaining = protein_gap = None
    if targets and targets.get("kcal"):
        status = (plan.get("today") or {})
        remaining = tuple(status["remaining_kcal"]) if summary["logged"] and status.get("remaining_kcal") else tuple(targets["kcal"])
    if targets and targets.get("protein_g"):
        if not summary["logged"]:
            protein_gap = float(targets["protein_g"][0])
        elif summary["protein_g"] is not None:
            protein_gap = float(targets["protein_g"][0]) - summary["protein_g"]
    gaps = foodsuggest.micro_gaps(nutrients.summarise([e["micros"] for e in view["entries"]]), (plan or {}).get("logged_days", 0))
    res = foodsuggest.suggest(candidates=cands, n_history=n_history, remaining_kcal=remaining, protein_gap_g=protein_gap, gaps=gaps,
                              slots_left=len(foodlog.MEALS) - foodlog.MEALS.index(meal), day_logged=summary["logged"])
    for s in res["suggestions"]:
        s["reasons"] = notes.food_suggestion_reasons(s)
        s["kcal"] = {"value": s["kcal"], "low": s.pop("kcal_low"), "high": s.pop("kcal_high")}
        s.pop("micros", None), s.pop("habit", None)
        s["facts"] = {k: s["facts"][k] for k in ("budget_kcal", "remaining_kcal", "protein_gap_g")}
    return {"status": res["status"], "needs": res["needs"], "day": day, "meal": meal,
            "reasons_note": notes.FOOD_SUGGEST_CAVEAT if res["status"] == "ok" else notes.FOOD_SUGGEST_EMPTY,
            "suggestions": res["suggestions"]}
