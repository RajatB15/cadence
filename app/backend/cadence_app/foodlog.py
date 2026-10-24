"""Food log: a personal dish library plus the meals eaten, tuned for home-cooked Indian food.

You log "2 roti + 1 katori dal" instead of searching a barcode database. Each dish stores nutrition for one serving
unit; a logged entry copies those numbers, so editing a dish later never rewrites history.

Nothing here is measured. The built-in dishes (catalogue/starter_dishes.json) are rounded, typical per-serving figures written for a starter library
(cross-check against the Indian Food Composition Tables, IFCT 2017, ICMR-National Institute of Nutrition); how you
cook (oil, ghee, portion size) moves them a lot, so edit a dish once to match your kitchen. Every entry carries a
spread (home-cooked ±20%, eating out ±30%, packaged ±10%) and daily totals are shown as ranges, never as exact.
A day with nothing logged is "not logged", not zero.
"""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from pathlib import Path

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from cadence_app.models import FoodDish, FoodEntry

MEALS = ("breakfast", "lunch", "snack", "dinner")
MAX_BACKFILL_DAYS = 60
MAX_SERVINGS = 20.0
MAX_KCAL = 5000.0
HOME_SPREAD, OUT_SPREAD, PACKAGED_SPREAD = 20, 30, 10
# Days with at least one entry needed before a multi-day average is shown.
MIN_DAYS_FOR_AVERAGE = 4
# ISSN position stand (Jäger et al. 2017): 1.4-2.0 g/kg/day for people who exercise. A reference range, not advice.
PROTEIN_REFERENCE_G_PER_KG = (1.4, 2.0)

STARTER_FILE = Path(__file__).parent / "catalogue" / "starter_dishes.json"


def starter_dishes() -> list[dict]:
    return json.loads(STARTER_FILE.read_text(encoding="utf-8"))["dishes"]


class FoodError(ValueError):
    pass


def ensure_catalogue(session: Session, now: datetime) -> None:
    """Adds any starter dish that's missing, by name; never touches one you edited or switched off."""
    existing = set(session.scalars(select(FoodDish.name)))
    added = False
    for d in starter_dishes():
        if d["name"] not in existing:
            session.add(FoodDish(name=d["name"], unit=d["unit"], kcal=d["kcal"], protein_g=d["protein_g"], carbs_g=d["carbs_g"],
                                 fat_g=d["fat_g"], spread_pct=d.get("spread_pct", HOME_SPREAD), builtin=True, active=True,
                                 created_at=now))
            added = True
    if added:
        session.commit()


def dish_dict(d: FoodDish) -> dict:
    return {"id": d.id, "name": d.name, "unit": d.unit, "kcal": d.kcal, "protein_g": d.protein_g, "carbs_g": d.carbs_g,
            "fat_g": d.fat_g, "spread_pct": d.spread_pct, "builtin": d.builtin, "active": d.active}


def dishes(session: Session, include_inactive: bool = False) -> list[dict]:
    q = select(FoodDish).order_by(FoodDish.name)
    if not include_inactive:
        q = q.where(FoodDish.active.is_(True))
    return [dish_dict(d) for d in session.scalars(q)]


def _clean(name: str, unit: str, kcal: float, protein_g: float, carbs_g: float, fat_g: float) -> tuple[str, str]:
    name, unit = name.strip(), unit.strip()
    if not name or not unit:
        raise FoodError("A dish needs a name and a serving unit")
    if not 0 <= kcal <= MAX_KCAL:
        raise FoodError(f"Calories per serving must be between 0 and {MAX_KCAL:g}")
    if min(protein_g, carbs_g, fat_g) < 0:
        raise FoodError("Macros can't be negative")
    return name[:80], unit[:40]


def add_dish(session: Session, name: str, unit: str, kcal: float, protein_g: float, carbs_g: float, fat_g: float,
             now: datetime, spread_pct: int = HOME_SPREAD) -> dict:
    name, unit = _clean(name, unit, kcal, protein_g, carbs_g, fat_g)
    if session.scalar(select(FoodDish.id).where(FoodDish.name == name)) is not None:
        raise FoodError("You already have a dish with that name")
    d = FoodDish(name=name, unit=unit, kcal=kcal, protein_g=protein_g, carbs_g=carbs_g, fat_g=fat_g,
                 spread_pct=spread_pct, builtin=False, active=True, created_at=now)
    session.add(d)
    session.commit()
    return dish_dict(d)


def update_dish(session: Session, dish_id: int, values: dict) -> dict | None:
    d = session.get(FoodDish, dish_id)
    if d is None:
        return None
    merged = {k: values.get(k) if values.get(k) is not None else getattr(d, k)
              for k in ("name", "unit", "kcal", "protein_g", "carbs_g", "fat_g", "spread_pct")}
    name, unit = _clean(merged["name"], merged["unit"], merged["kcal"], merged["protein_g"], merged["carbs_g"], merged["fat_g"])
    clash = session.scalar(select(FoodDish.id).where(FoodDish.name == name, FoodDish.id != dish_id))
    if clash is not None:
        raise FoodError("You already have a dish with that name")
    d.name, d.unit = name, unit
    d.kcal, d.protein_g, d.carbs_g, d.fat_g, d.spread_pct = (merged[k] for k in ("kcal", "protein_g", "carbs_g", "fat_g", "spread_pct"))
    if values.get("active") is not None:
        d.active = values["active"]
    session.commit()
    return dish_dict(d)


def _check_day(day: date, today: date) -> None:
    if day > today:
        raise FoodError("Can't log food in the future")
    if day < today - timedelta(days=MAX_BACKFILL_DAYS):
        raise FoodError(f"Food logs cover today and the last {MAX_BACKFILL_DAYS} days")


def _check_meal(meal: str) -> None:
    if meal not in MEALS:
        raise FoodError("Unknown meal")


def log_dish(session: Session, day: date, meal: str, dish_id: int, servings: float, eating_out: bool,
             today: date, now: datetime) -> dict:
    _check_day(day, today)
    _check_meal(meal)
    if not 0 < servings <= MAX_SERVINGS:
        raise FoodError(f"Servings must be between 0 and {MAX_SERVINGS:g}")
    d = session.get(FoodDish, dish_id)
    if d is None:
        raise FoodError("Unknown dish")
    entry = FoodEntry(day=day, meal=meal, dish_id=d.id, name=d.name, servings=servings,
                      kcal=d.kcal * servings, protein_g=d.protein_g * servings, carbs_g=d.carbs_g * servings,
                      fat_g=d.fat_g * servings, spread_pct=max(d.spread_pct, OUT_SPREAD) if eating_out else d.spread_pct,
                      logged_at=now)
    session.add(entry)
    session.commit()
    return entry_dict(entry)


def log_quick(session: Session, day: date, meal: str, name: str, kcal: float, protein_g: float | None,
              today: date, now: datetime) -> dict:
    """A one-off entry (eating out, something not in the library). Calories required; protein optional."""
    _check_day(day, today)
    _check_meal(meal)
    if not name.strip():
        raise FoodError("Say what it was")
    if not 0 < kcal <= MAX_KCAL:
        raise FoodError(f"Calories must be between 0 and {MAX_KCAL:g}")
    if protein_g is not None and not 0 <= protein_g <= 500:
        raise FoodError("Protein must be between 0 and 500 g")
    entry = FoodEntry(day=day, meal=meal, dish_id=None, name=name.strip()[:80], servings=1, kcal=kcal,
                      protein_g=protein_g, carbs_g=None, fat_g=None, spread_pct=OUT_SPREAD, logged_at=now)
    session.add(entry)
    session.commit()
    return entry_dict(entry)


def remove(session: Session, entry_id: int) -> bool:
    result = session.execute(delete(FoodEntry).where(FoodEntry.id == entry_id))
    session.commit()
    return result.rowcount > 0


def copy_day(session: Session, source: date, target: date, today: date, now: datetime) -> int:
    """Copies a day's entries onto another day (typically yesterday onto today). Returns how many were added."""
    _check_day(target, today)
    rows = list(session.scalars(select(FoodEntry).where(FoodEntry.day == source).order_by(FoodEntry.id)))
    for r in rows:
        session.add(FoodEntry(day=target, meal=r.meal, dish_id=r.dish_id, name=r.name, servings=r.servings, kcal=r.kcal,
                              protein_g=r.protein_g, carbs_g=r.carbs_g, fat_g=r.fat_g, spread_pct=r.spread_pct, logged_at=now))
    session.commit()
    return len(rows)


def entry_dict(e: FoodEntry) -> dict:
    return {"id": e.id, "day": e.day, "meal": e.meal, "dish_id": e.dish_id, "name": e.name, "servings": e.servings,
            "kcal": round(e.kcal), "protein_g": None if e.protein_g is None else round(e.protein_g, 1),
            "carbs_g": None if e.carbs_g is None else round(e.carbs_g, 1),
            "fat_g": None if e.fat_g is None else round(e.fat_g, 1), "spread_pct": e.spread_pct}


def recent_dish_ids(session: Session, limit: int = 12) -> list[int]:
    """The dishes you log most often lately, so the picker can lead with them."""
    since = session.scalar(select(FoodEntry.day).order_by(FoodEntry.day.desc()).limit(1))
    if since is None:
        return []
    rows = session.execute(
        select(FoodEntry.dish_id).where(FoodEntry.dish_id.is_not(None), FoodEntry.day >= since - timedelta(days=30))
    ).scalars()
    counts: dict[int, int] = {}
    for dish_id in rows:
        counts[dish_id] = counts.get(dish_id, 0) + 1
    return [k for k, _ in sorted(counts.items(), key=lambda kv: -kv[1])[:limit]]


def day_summary(entries: list[dict], weight_kg: float | None = None) -> dict:
    """Totals for one day from its entries. Pure. Empty means not logged (all None), never zero."""
    if not entries:
        return {"logged": False, "entries": 0, "kcal": None, "kcal_low": None, "kcal_high": None, "protein_g": None,
                "carbs_g": None, "fat_g": None, "protein_g_per_kg": None, "partial_macros": False}
    kcal = sum(e["kcal"] for e in entries)
    low = sum(e["kcal"] * (1 - e["spread_pct"] / 100) for e in entries)
    high = sum(e["kcal"] * (1 + e["spread_pct"] / 100) for e in entries)

    def total(key: str) -> float | None:
        vals = [e[key] for e in entries if e[key] is not None]
        return round(sum(vals), 1) if vals else None

    protein = total("protein_g")
    return {
        "logged": True,
        "entries": len(entries),
        "kcal": round(kcal),
        "kcal_low": round(low),
        "kcal_high": round(high),
        "protein_g": protein,
        "carbs_g": total("carbs_g"),
        "fat_g": total("fat_g"),
        # Quick entries may lack macros, so the macro totals can be an undercount.
        "partial_macros": any(e["protein_g"] is None or e["carbs_g"] is None or e["fat_g"] is None for e in entries),
        "protein_g_per_kg": round(protein / weight_kg, 2) if protein is not None and weight_kg else None,
    }


def average(summaries: list[dict]) -> dict | None:
    """Average over logged days only; None until there are enough of them to say anything."""
    logged = [s for s in summaries if s["logged"]]
    if len(logged) < MIN_DAYS_FOR_AVERAGE:
        return None
    n = len(logged)
    protein = [s["protein_g"] for s in logged if s["protein_g"] is not None]
    return {
        "days_logged": n,
        "days_covered": len(summaries),
        "kcal": round(sum(s["kcal"] for s in logged) / n),
        "kcal_low": round(sum(s["kcal_low"] for s in logged) / n),
        "kcal_high": round(sum(s["kcal_high"] for s in logged) / n),
        "protein_g": round(sum(protein) / len(protein), 1) if protein else None,
    }


def view(session: Session, day: date, today: date, weight_kg: float | None, window: int = 7) -> dict:
    """Everything the Food page needs for one day, plus a trailing window of day totals."""
    since = day - timedelta(days=window - 1)
    rows = list(session.scalars(select(FoodEntry).where(FoodEntry.day >= since, FoodEntry.day <= day).order_by(FoodEntry.id)))
    by_day: dict[date, list[dict]] = {}
    for r in rows:
        by_day.setdefault(r.day, []).append(entry_dict(r))
    trail = []
    for i in range(window):
        d = since + timedelta(days=i)
        trail.append({"day": d, **day_summary(by_day.get(d, []), weight_kg)})
    return {
        "day": day,
        "today": today,
        "entries": by_day.get(day, []),
        "summary": day_summary(by_day.get(day, []), weight_kg),
        "trail": trail,
        "average": average(trail),
        "weight_kg": weight_kg,
        "protein_reference_g_per_kg": PROTEIN_REFERENCE_G_PER_KG,
        "recent_dish_ids": recent_dish_ids(session),
    }
