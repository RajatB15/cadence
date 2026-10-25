"""Food log: a personal dish library plus the meals eaten, tuned for home-cooked Indian food.

You log "2 roti + 1 katori dal" instead of searching a barcode database. Each dish stores nutrition per 100 g and the
weight of its household portions; a logged entry copies the numbers, so editing a dish later never rewrites history.

Nothing here is measured. The built-in dishes come from a personal-use crawl of the food library kept in the
private `food-data` submodule (see `food_import`): per-100 g values calculated from recipes found on the web, marked
unverified, so each dish shows its source. How you cook (oil, ghee, portion size) moves them a lot, so edit a dish once
to match your kitchen. Every entry carries a spread (built-in 25%, eating out 30%) and daily totals are shown as
ranges, never as exact. A day with nothing logged is "not logged", not zero.
"""

from __future__ import annotations

import json
import re
from datetime import date, datetime, timedelta
from functools import lru_cache
from pathlib import Path

from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from cadence_app import nutrients
from cadence_app.models import FoodDish, FoodEntry, FoodMeal, FoodMealItem

MEALS = ("breakfast", "lunch", "snack", "dinner")
MAX_BACKFILL_DAYS = 60
MAX_SERVINGS = 20.0
MAX_UNIT_GRAMS = 3000.0
MAX_LOG_GRAMS = 5000.0
MAX_KCAL = 5000.0
HOME_SPREAD, OUT_SPREAD, PACKAGED_SPREAD = 20, 30, 10
# Days with at least one entry needed before a multi-day average is shown.
MIN_DAYS_FOR_AVERAGE = 4
# ISSN position stand (Jäger et al. 2017): 1.4-2.0 g/kg/day for people who exercise. A reference range, not advice.
PROTEIN_REFERENCE_G_PER_KG = (1.4, 2.0)

class FoodError(ValueError):
    pass


MIN_CATALOGUE_TO_RETIRE_OLD = 100  # only retire the older built-in dishes once a real catalogue is loaded
OLD_SOURCES = ("starter", "INDB", "IFCT")
_APPLIED: dict[str, tuple] = {}


@lru_cache(maxsize=2)
def _read_catalogue(path: str, mtime: float) -> tuple[dict, ...]:
    return tuple(json.loads(Path(path).read_text(encoding="utf-8"))["dishes"])


def catalogue_dishes(food_data_dir: Path | None) -> tuple[dict, ...]:
    """Dishes built by `food_import` from the food-data submodule; empty when it isn't there or isn't built."""
    if food_data_dir is None:
        return ()
    path = food_data_dir / "library" / "catalogue.json"
    try:
        return _read_catalogue(str(path), path.stat().st_mtime)
    except (OSError, ValueError, KeyError):
        return ()


def _apply(row: FoodDish, d: dict) -> None:
    row.name, row.unit = d["name"], d["unit"]
    row.kcal, row.protein_g, row.carbs_g, row.fat_g = (round(d[k], 1) for k in ("kcal", "protein_g", "carbs_g", "fat_g"))
    row.unit_g = d["grams"]
    per100 = d["per_100g"]
    row.kcal_100g, row.protein_100g, row.carbs_100g, row.fat_100g = (per100[k] for k in ("kcal", "protein_g", "carbs_g", "fat_g"))
    row.spread_pct = d.get("spread_pct", HOME_SPREAD)
    row.basis, row.note, row.flagged = d.get("basis", "library"), d.get("note"), False
    row.aliases = json.dumps(d["aliases"], ensure_ascii=False) if d.get("aliases") else None
    row.portions = json.dumps(d["portions"], ensure_ascii=False) if d.get("portions") else None
    row.micros_100g = json.dumps(d["micros_per_100g"]) if d.get("micros_per_100g") else None
    row.builtin = True


def ensure_catalogue(session: Session, now: datetime, food_data_dir: Path | None = None) -> None:
    """Adds missing catalogue dishes and refreshes the ones you haven't edited.

    Matching is by the catalogue code, so your own dishes are never touched and nothing is added twice. A built-in dish
    you edited keeps your numbers. Once a real catalogue is loaded the older built-in dishes (starter, INDB, IFCT) are
    removed: logged entries keep their own copy of the numbers, and any older dish you had edited becomes your own.
    """
    path = food_data_dir / "library" / "catalogue.json" if food_data_dir else None
    stamp = path.stat().st_mtime if path and path.is_file() else None
    key = str(session.get_bind().url)
    if _APPLIED.get(key) == stamp:
        return
    catalogue = catalogue_dishes(food_data_dir)
    if len(catalogue) < MIN_CATALOGUE_TO_RETIRE_OLD:
        _APPLIED[key] = stamp
        return
    rows, removed = list(session.scalars(select(FoodDish))), set()
    for r in rows:
        if r.source in OLD_SOURCES:
            if r.edited:
                r.source, r.builtin, r.ref_code = "mine", False, None
            else:
                session.delete(r)
                removed.add(r.id)
    session.flush()
    rows = [r for r in rows if r.id not in removed]
    library = sorted((r for r in rows if r.source == "library"), key=lambda r: (not r.edited, r.id))
    by_code: dict[str, list[FoodDish]] = {}
    for r in library:
        if r.ref_code:
            by_code.setdefault(r.ref_code, []).append(r)
    # A dish may be stored under a page code from an earlier build (the code used to follow whichever page named the group).
    # Find every stored row for each catalogue dish: keep one, fold the rest into it.
    plan: list[tuple[dict, FoodDish | None]] = []
    used: set[int] = set()
    for d in catalogue:
        found, seen = [], set()
        for code in [d["ref_code"], *d.get("page_codes", [])]:
            for r in by_code.get(code, []):
                if r.id not in seen and r.id not in used:
                    seen.add(r.id)
                    found.append(r)
        found.sort(key=lambda r: (not r.edited, r.id))
        keep = found[0] if found else None
        for extra in found[1:]:
            used.add(extra.id)
            if extra.edited:
                extra.source, extra.builtin, extra.ref_code = "mine", False, None
            else:
                session.execute(update(FoodEntry).where(FoodEntry.dish_id == extra.id).values(dish_id=keep.id))
                session.delete(extra)
        if keep:
            used.add(keep.id)
        plan.append((d, keep))
    for r in library:  # no longer in the catalogue at all (its page was dropped by a stricter rule)
        if r.id not in used:
            if r.edited:
                r.source, r.builtin, r.ref_code = "mine", False, None
            else:
                session.delete(r)
    session.flush()
    for d, row in plan:  # names are unique: free the ones about to change so two dishes can swap
        if row is not None and row.name != d["name"]:
            row.name = f"\0{row.id}"
    session.flush()
    taken = {r.name.lower() for r in session.scalars(select(FoodDish)) if r.source != "library"}
    for d, row in plan:
        if row is None:
            if d["name"].lower() in taken:  # one of your own dishes already has this name
                continue
            row = FoodDish(name=d["name"], builtin=True, active=True, source="library", created_at=now)
            session.add(row)
        elif row.edited:
            row.ref_code = d["ref_code"]
            row.micros_100g = json.dumps(d["micros_per_100g"]) if d.get("micros_per_100g") else None  # nutrient tables are not user-editable
            continue
        row.ref_code = d["ref_code"]
        _apply(row, d)
        taken.add(d["name"].lower())
    session.commit()
    _APPLIED[key] = stamp


def dish_dict(d: FoodDish) -> dict:
    return {"id": d.id, "name": d.name, "unit": d.unit, "kcal": d.kcal, "protein_g": d.protein_g, "carbs_g": d.carbs_g,
            "fat_g": d.fat_g, "spread_pct": d.spread_pct, "builtin": d.builtin, "active": d.active, "source": d.source,
            "ref_code": d.ref_code, "unit_g": d.unit_g, "basis": d.basis, "note": d.note, "flagged": d.flagged,
            "per_100g": None if d.kcal_100g is None else {"kcal": d.kcal_100g, "protein_g": d.protein_100g,
                                                          "carbs_g": d.carbs_100g, "fat_g": d.fat_100g},
            "micros_per_100g": json.loads(d.micros_100g) if d.micros_100g else None,
            "aliases": json.loads(d.aliases) if d.aliases else [],
            "portions": json.loads(d.portions) if d.portions else [],
            "grams_ok": d.unit_g is not None and d.kcal_100g is not None}


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
             now: datetime, spread_pct: int = HOME_SPREAD, grams: float | None = None) -> dict:
    """Your own dish. Give the weight of one serving (grams) and it can also be logged by weight."""
    name, unit = _clean(name, unit, kcal, protein_g, carbs_g, fat_g)
    if session.scalar(select(FoodDish.id).where(FoodDish.name == name)) is not None:
        raise FoodError("You already have a dish with that name")
    d = FoodDish(name=name, unit=unit, kcal=kcal, protein_g=protein_g, carbs_g=carbs_g, fat_g=fat_g,
                 spread_pct=spread_pct, builtin=False, active=True, source="mine", basis="estimate", created_at=now)
    _set_weight(d, grams)
    session.add(d)
    session.commit()
    return dish_dict(d)


def _set_weight(d: FoodDish, grams: float | None) -> None:
    """Keeps per-serving and per-100 g consistent: both come from the per-serving numbers and the serving weight."""
    if not grams:
        d.unit_g = d.kcal_100g = d.protein_100g = d.carbs_100g = d.fat_100g = None
        return
    if not 0 < grams <= MAX_UNIT_GRAMS:
        raise FoodError(f"A serving weighs between 0 and {MAX_UNIT_GRAMS:g} g")
    d.unit_g = grams
    d.kcal_100g, d.protein_100g = round(d.kcal / grams * 100, 1), round(d.protein_g / grams * 100, 1)
    d.carbs_100g, d.fat_100g = round(d.carbs_g / grams * 100, 1), round(d.fat_g / grams * 100, 1)


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
    nutrition_changed = any(values.get(k) is not None for k in ("kcal", "protein_g", "carbs_g", "fat_g")) or values.get("grams") is not None
    d.name, d.unit = name, unit
    d.kcal, d.protein_g, d.carbs_g, d.fat_g, d.spread_pct = (merged[k] for k in ("kcal", "protein_g", "carbs_g", "fat_g", "spread_pct"))
    if values.get("active") is not None:
        d.active = values["active"]
    if nutrition_changed:
        _set_weight(d, values["grams"] if values.get("grams") is not None else d.unit_g)
        d.basis, d.note, d.flagged = "estimate", "Edited by you.", False
    d.edited = d.edited or any(values.get(k) is not None for k in ("name", "unit", "kcal", "protein_g", "carbs_g", "fat_g", "spread_pct", "grams"))
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


def _portion(d: FoodDish, servings: float, grams: float | None) -> dict:
    """What eating `servings` (or `grams`) of a dish adds up to: the amounts, plus the micronutrients when its weight is known."""
    has_weight = dish_dict(d)["grams_ok"]
    if grams is not None:
        if not has_weight:
            raise FoodError("This dish is logged by serving, not by grams")
        if not 0 < grams <= MAX_LOG_GRAMS:
            raise FoodError(f"Grams must be between 0 and {MAX_LOG_GRAMS:g}")
        servings = grams / d.unit_g
        kcal, protein, carbs, fat = (v * grams / 100 for v in (d.kcal_100g, d.protein_100g, d.carbs_100g, d.fat_100g))
    else:
        if not 0 < servings <= MAX_SERVINGS:
            raise FoodError(f"Servings must be between 0 and {MAX_SERVINGS:g}")
        kcal, protein, carbs, fat = (v * servings for v in (d.kcal, d.protein_g, d.carbs_g, d.fat_g))
        grams = round(servings * d.unit_g, 1) if has_weight else None
    micros = nutrients.scale(json.loads(d.micros_100g) if d.micros_100g else None, grams)
    return {"servings": servings, "grams": grams, "kcal": kcal, "protein_g": protein, "carbs_g": carbs, "fat_g": fat, "micros": micros}


def _micros_json(m: dict | None) -> str | None:
    return json.dumps(m) if m else None


def log_dish(session: Session, day: date, meal: str, dish_id: int, servings: float, eating_out: bool,
             today: date, now: datetime, grams: float | None = None) -> dict:
    """Logs a dish by number of servings, or by grams for dishes that have a weight."""
    _check_day(day, today)
    _check_meal(meal)
    d = session.get(FoodDish, dish_id)
    if d is None:
        raise FoodError("Unknown dish")
    p = _portion(d, servings, grams)
    entry = FoodEntry(day=day, meal=meal, dish_id=d.id, name=d.name, servings=p["servings"], kcal=p["kcal"],
                      protein_g=p["protein_g"], carbs_g=p["carbs_g"], fat_g=p["fat_g"], grams=p["grams"],
                      micros=_micros_json(p["micros"]),
                      spread_pct=max(d.spread_pct, OUT_SPREAD) if eating_out else d.spread_pct, logged_at=now)
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
                              protein_g=r.protein_g, carbs_g=r.carbs_g, fat_g=r.fat_g, grams=r.grams, micros=r.micros,
                              spread_pct=r.spread_pct, logged_at=now))
    session.commit()
    return len(rows)


def entry_dict(e: FoodEntry) -> dict:
    return {"id": e.id, "day": e.day, "meal": e.meal, "dish_id": e.dish_id, "name": e.name, "servings": e.servings,
            "kcal": round(e.kcal), "protein_g": None if e.protein_g is None else round(e.protein_g, 1),
            "carbs_g": None if e.carbs_g is None else round(e.carbs_g, 1),
            "fat_g": None if e.fat_g is None else round(e.fat_g, 1), "spread_pct": e.spread_pct,
            "grams": None if e.grams is None else round(e.grams),
            "micros": json.loads(e.micros) if e.micros else None}


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


def view(session: Session, day: date, today: date, weight_kg: float | None, window: int = 7, long_window: int = 14) -> dict:
    """Everything the Food page needs for one day, plus trailing windows of day totals (7 shown, 14 for the expenditure check)."""
    since = day - timedelta(days=long_window - 1)
    rows = list(session.scalars(select(FoodEntry).where(FoodEntry.day >= since, FoodEntry.day <= day).order_by(FoodEntry.id)))
    by_day: dict[date, list[dict]] = {}
    for r in rows:
        by_day.setdefault(r.day, []).append(entry_dict(r))
    trail14 = []
    for i in range(long_window):
        d = since + timedelta(days=i)
        trail14.append({"day": d, **day_summary(by_day.get(d, []), weight_kg)})
    trail = trail14[-window:]
    return {
        "day": day,
        "today": today,
        "entries": by_day.get(day, []),
        "summary": day_summary(by_day.get(day, []), weight_kg),
        "trail": trail,
        "trail14": trail14,
        "average": average(trail),
        "weight_kg": weight_kg,
        "protein_reference_g_per_kg": PROTEIN_REFERENCE_G_PER_KG,
        "recent_dish_ids": recent_dish_ids(session),
        "micros": nutrients.summarise([e["micros"] for e in by_day.get(day, [])]),
    }


def set_amount(session: Session, entry_id: int, servings: float) -> dict | None:
    """Changes how much of an entry was eaten, scaling everything it holds (calories, macros, grams, micronutrients)."""
    e = session.get(FoodEntry, entry_id)
    if e is None:
        return None
    if not 0 < servings <= MAX_SERVINGS:
        raise FoodError(f"Servings must be between 0 and {MAX_SERVINGS:g}")
    factor = servings / e.servings
    e.kcal = e.kcal * factor
    for attr in ("protein_g", "carbs_g", "fat_g", "grams"):
        v = getattr(e, attr)
        setattr(e, attr, None if v is None else v * factor)
    e.micros = _micros_json(nutrients.multiply(json.loads(e.micros) if e.micros else None, factor))
    e.servings = servings
    session.commit()
    return entry_dict(e)


# ---- saved meals: a few foods eaten together, logged in one tap ----

MAX_MEAL_ITEMS = 20
MAX_MEAL_SCALE = 5.0


def _item_values(item: FoodMealItem, dish: FoodDish | None) -> dict:
    """What a meal item adds up to now: from the dish as it is today (so editing a dish carries through), else the copy saved with the meal."""
    if dish is not None and dish.active:
        try:
            return _portion(dish, item.servings, item.grams if item.grams and dish_dict(dish)["grams_ok"] else None)
        except FoodError:
            pass
    return {"servings": item.servings, "grams": item.grams, "kcal": item.kcal, "protein_g": item.protein_g, "carbs_g": item.carbs_g,
            "fat_g": item.fat_g, "micros": json.loads(item.micros) if item.micros else None}


def meal_dict(session: Session, m: FoodMeal) -> dict:
    items = list(session.scalars(select(FoodMealItem).where(FoodMealItem.meal_id == m.id).order_by(FoodMealItem.position, FoodMealItem.id)))
    out, total = [], {"kcal": 0.0, "protein_g": 0.0, "carbs_g": 0.0, "fat_g": 0.0}
    partial = False
    for it in items:
        v = _item_values(it, session.get(FoodDish, it.dish_id) if it.dish_id else None)
        out.append({"id": it.id, "dish_id": it.dish_id, "name": it.name, "servings": round(v["servings"], 2),
                    "grams": None if v["grams"] is None else round(v["grams"]), "kcal": round(v["kcal"]),
                    "protein_g": None if v["protein_g"] is None else round(v["protein_g"], 1)})
        total["kcal"] += v["kcal"]
        for k in ("protein_g", "carbs_g", "fat_g"):
            if v[k] is None:
                partial = True
            else:
                total[k] += v[k]
    return {"id": m.id, "name": m.name, "items": out, "kcal": round(total["kcal"]), "protein_g": round(total["protein_g"], 1),
            "carbs_g": round(total["carbs_g"], 1), "fat_g": round(total["fat_g"], 1), "partial_macros": partial,
            "last_used": m.last_used}


def meals(session: Session) -> list[dict]:
    """Saved meals, most recently used first, then newest."""
    rows = list(session.scalars(select(FoodMeal)))
    rows.sort(key=lambda m: (m.last_used or datetime.min, m.created_at), reverse=True)
    return [meal_dict(session, m) for m in rows]


def save_meal(session: Session, name: str, entry_ids: list[int], now: datetime) -> dict:
    """Groups logged entries under a name of your own. Foods linked to a dish are saved by dish and amount."""
    name = name.strip()[:80]
    if not name:
        raise FoodError("Give the meal a name")
    if not entry_ids:
        raise FoodError("Pick at least one food")
    if len(entry_ids) > MAX_MEAL_ITEMS:
        raise FoodError(f"A meal holds up to {MAX_MEAL_ITEMS} foods")
    if session.scalar(select(FoodMeal.id).where(FoodMeal.name.ilike(name))) is not None:
        raise FoodError("You already have a meal with that name")
    by_id = {e.id: e for e in session.scalars(select(FoodEntry).where(FoodEntry.id.in_(entry_ids)))}
    if len(by_id) != len(set(entry_ids)):
        raise FoodError("One of those foods no longer exists")
    meal = FoodMeal(name=name, created_at=now)
    session.add(meal)
    session.flush()
    for pos, eid in enumerate(dict.fromkeys(entry_ids)):
        e = by_id[eid]
        session.add(FoodMealItem(meal_id=meal.id, position=pos, dish_id=e.dish_id, name=e.name, servings=e.servings, grams=e.grams,
                                 kcal=e.kcal, protein_g=e.protein_g, carbs_g=e.carbs_g, fat_g=e.fat_g, spread_pct=e.spread_pct,
                                 micros=e.micros))
    session.commit()
    return meal_dict(session, meal)


def rename_meal(session: Session, meal_id: int, name: str) -> dict | None:
    m = session.get(FoodMeal, meal_id)
    if m is None:
        return None
    name = name.strip()[:80]
    if not name:
        raise FoodError("Give the meal a name")
    if session.scalar(select(FoodMeal.id).where(FoodMeal.name.ilike(name), FoodMeal.id != meal_id)) is not None:
        raise FoodError("You already have a meal with that name")
    m.name = name
    session.commit()
    return meal_dict(session, m)


def delete_meal(session: Session, meal_id: int) -> bool:
    session.execute(delete(FoodMealItem).where(FoodMealItem.meal_id == meal_id))
    result = session.execute(delete(FoodMeal).where(FoodMeal.id == meal_id))
    session.commit()
    return result.rowcount > 0


def log_meal(session: Session, meal_id: int, day: date, meal: str, scale: float, eating_out: bool, today: date, now: datetime) -> list[dict]:
    """Adds every food in a saved meal to a day, optionally scaled (0.5 = half portions)."""
    _check_day(day, today)
    _check_meal(meal)
    if not 0 < scale <= MAX_MEAL_SCALE:
        raise FoodError(f"Scale must be between 0 and {MAX_MEAL_SCALE:g}")
    m = session.get(FoodMeal, meal_id)
    if m is None:
        raise FoodError("Unknown meal")
    items = list(session.scalars(select(FoodMealItem).where(FoodMealItem.meal_id == m.id).order_by(FoodMealItem.position, FoodMealItem.id)))
    added = []
    for it in items:
        dish = session.get(FoodDish, it.dish_id) if it.dish_id else None
        v = _item_values(it, dish)
        factor = scale
        spread = it.spread_pct if dish is None else dish.spread_pct
        entry = FoodEntry(day=day, meal=meal, dish_id=dish.id if dish else None, name=it.name, servings=v["servings"] * factor,
                          kcal=v["kcal"] * factor, protein_g=None if v["protein_g"] is None else v["protein_g"] * factor,
                          carbs_g=None if v["carbs_g"] is None else v["carbs_g"] * factor,
                          fat_g=None if v["fat_g"] is None else v["fat_g"] * factor,
                          grams=None if v["grams"] is None else v["grams"] * factor,
                          micros=_micros_json(nutrients.multiply(v["micros"], factor)),
                          spread_pct=max(spread, OUT_SPREAD) if eating_out else spread, logged_at=now)
        session.add(entry)
        added.append(entry)
    m.last_used = now
    session.commit()
    return [entry_dict(e) for e in added]
