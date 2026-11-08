"""Food log: a personal dish library plus the meals eaten, tuned for home-cooked Indian food.

You log "2 roti + 1 katori dal" instead of searching a barcode database. Each dish stores nutrition per 100 g and the
weight of its household portions; a logged entry copies the numbers, so editing a dish later never rewrites history.

Nothing here is measured. The built-in dishes come from a personal-use crawl of a public nutrition database kept in the
private `food-data` submodule (see `food_import`): per-100 g values calculated from recipes found on the web, marked
unverified, so each dish shows its source. How you cook (oil, ghee, portion size) moves them a lot, so edit a dish once
to match your kitchen. Every entry carries a spread (built-in 25%, eating out 30%) and daily totals are shown as
ranges, never as exact. A day with nothing logged is "not logged", not zero.
"""

from __future__ import annotations

import json
import re
import threading
from datetime import date, datetime, time, timedelta, timezone
from functools import lru_cache
from pathlib import Path

from sqlalchemy import delete, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from cadence_app import nutrients
from cadence_app.analytics import foodrank
from cadence_app.models import FoodDish, FoodEntry, FoodMeal, FoodMealItem, FoodPortionMemory

MEALS = ("breakfast", "lunch", "snack", "dinner")
SOURCES = ("manual", "quick", "chip", "scan", "copy")
MAX_BATCH_ITEMS = 40
MAX_BULK_IDS = 100
KEY_MAX = 56  # a batch item's key is "{key}:{index}" and must fit the 64-character column
PURGE_AFTER_DAYS = 7
BARCODE_RE = re.compile(r"[0-9]{6,14}")
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

def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class FoodError(ValueError):
    pass


MIN_CATALOGUE_TO_RETIRE_OLD = 100  # only retire the older built-in dishes once a real catalogue is loaded
OLD_SOURCES = ("starter", "INDB", "IFCT")
_APPLIED: dict[str, tuple] = {}
_APPLY_LOCK = threading.Lock()  # two first requests must not both insert the library (names are unique)


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
    path = food_data_dir / "library" / "catalogue.json" if food_data_dir else None
    stamp = path.stat().st_mtime if path and path.is_file() else None
    if _APPLIED.get(str(session.get_bind().url)) == stamp:
        return
    with _APPLY_LOCK:  # the second caller waits, then finds it already applied
        session.rollback()  # see what the first caller committed, not a stale snapshot
        _ensure_catalogue(session, now, food_data_dir)


def _ensure_catalogue(session: Session, now: datetime, food_data_dir: Path | None = None) -> None:
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
            "grams_ok": d.unit_g is not None and d.kcal_100g is not None, "barcode": d.barcode, "pinned": bool(d.pinned)}


def dishes(session: Session, include_inactive: bool = False) -> list[dict]:
    q = select(FoodDish).order_by(FoodDish.name)
    if not include_inactive:
        q = q.where(FoodDish.active.is_(True))
    return [dish_dict(d) for d in session.scalars(q)]


def _clean(name: str, unit: str, kcal: float, protein_g: float | None, carbs_g: float | None, fat_g: float | None) -> tuple[str, str]:
    name, unit = name.strip(), unit.strip()
    if not name or not unit:
        raise FoodError("A dish needs a name and a serving unit")
    if not 0 <= kcal <= MAX_KCAL:
        raise FoodError(f"Calories per serving must be between 0 and {MAX_KCAL:g}")
    if min((v for v in (protein_g, carbs_g, fat_g) if v is not None), default=0) < 0:
        raise FoodError("Macros can't be negative")
    return name[:80], unit[:40]


def _clean_micros(micros: dict | None) -> dict[str, float] | None:
    """Only tracked nutrients with sensible non-negative amounts per 100 g; anything else is dropped, not guessed."""
    out = {k: round(float(v), 2) for k, v in (micros or {}).items() if k in nutrients.KEYS and isinstance(v, (int, float)) and 0 <= v <= 100000}
    return out or None


def add_dish(session: Session, name: str, unit: str, kcal: float, protein_g: float | None, carbs_g: float | None, fat_g: float | None,
             now: datetime, spread_pct: int = HOME_SPREAD, grams: float | None = None, micros_per_100g: dict | None = None,
             basis: str = "estimate", note: str | None = None, barcode: str | None = None) -> dict:
    """Your own dish (typed in, read from a label, or remembered from a quick entry). Give the weight of one serving
    (grams) and it can also be logged by weight. Macros you don't know stay unknown."""
    name, unit = _clean(name, unit, kcal, protein_g, carbs_g, fat_g)
    if session.scalar(select(FoodDish.id).where(FoodDish.name == name)) is not None:
        raise FoodError("You already have a dish with that name")
    d = FoodDish(name=name, unit=unit, kcal=kcal, protein_g=protein_g, carbs_g=carbs_g, fat_g=fat_g,
                 spread_pct=spread_pct, builtin=False, active=True, source="mine", basis=basis, note=note, created_at=now)
    _set_weight(d, grams)
    micros = _clean_micros(micros_per_100g)
    d.micros_100g = json.dumps(micros) if micros and d.unit_g else None  # per 100 g needs a weight to scale from
    if barcode:
        d.barcode = _free_barcode(session, barcode, None)
    session.add(d)
    session.commit()
    return dish_dict(d)


def clean_barcode(code: str | None) -> str | None:
    """Digits only, 6 to 14 of them (EAN-8/13, UPC-A/E, ITF-14). Typed codes may carry spaces or dashes."""
    code = re.sub(r"[\s-]", "", code or "")
    if not code:
        return None
    if not BARCODE_RE.fullmatch(code):
        raise FoodError("A barcode is 6 to 14 digits")
    return code


def _free_barcode(session: Session, code: str, dish_id: int | None) -> str:
    code = clean_barcode(code)
    clash = session.scalar(select(FoodDish).where(FoodDish.barcode == code, FoodDish.id != (dish_id or 0)))
    if clash is not None:
        raise FoodError(f"That barcode already belongs to {clash.name}")
    return code


def _set_weight(d: FoodDish, grams: float | None) -> None:
    """Keeps per-serving and per-100 g consistent: both come from the per-serving numbers and the serving weight."""
    if not grams:
        d.unit_g = d.kcal_100g = d.protein_100g = d.carbs_100g = d.fat_100g = None
        return
    if not 0 < grams <= MAX_UNIT_GRAMS:
        raise FoodError(f"A serving weighs between 0 and {MAX_UNIT_GRAMS:g} g")
    d.unit_g = grams
    per100 = lambda v: None if v is None else round(v / grams * 100, 1)  # noqa: E731
    d.kcal_100g, d.protein_100g = per100(d.kcal), per100(d.protein_g)
    d.carbs_100g, d.fat_100g = per100(d.carbs_g), per100(d.fat_g)


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
    if values.get("pinned") is not None:
        d.pinned = bool(values["pinned"])
    if "barcode" in values:  # null or empty clears it
        d.barcode = _free_barcode(session, values["barcode"], dish_id) if clean_barcode(values["barcode"]) else None
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


def _times(value: float | None, factor: float) -> float | None:
    return None if value is None else value * factor


def _portion(d: FoodDish, servings: float, grams: float | None) -> dict:
    """What eating `servings` (or `grams`) of a dish adds up to: the amounts, plus the micronutrients when its weight is known."""
    has_weight = dish_dict(d)["grams_ok"]
    if grams is not None:
        if not has_weight:
            raise FoodError("This dish is logged by serving, not by grams")
        if not 0 < grams <= MAX_LOG_GRAMS:
            raise FoodError(f"Grams must be between 0 and {MAX_LOG_GRAMS:g}")
        servings = grams / d.unit_g
        kcal, protein, carbs, fat = (_times(v, grams / 100) for v in (d.kcal_100g, d.protein_100g, d.carbs_100g, d.fat_100g))
    else:
        if not 0 < servings <= MAX_SERVINGS:
            raise FoodError(f"Servings must be between 0 and {MAX_SERVINGS:g}")
        kcal, protein, carbs, fat = (_times(v, servings) for v in (d.kcal, d.protein_g, d.carbs_g, d.fat_g))
        grams = round(servings * d.unit_g, 1) if has_weight else None
    micros = nutrients.scale(json.loads(d.micros_100g) if d.micros_100g else None, grams)
    return {"servings": servings, "grams": grams, "kcal": kcal, "protein_g": protein, "carbs_g": carbs, "fat_g": fat, "micros": micros}


def _micros_json(m: dict | None) -> str | None:
    return json.dumps(m) if m else None


def parse_eaten_at(value: str | time | None) -> time | None:
    """"HH:MM" (or HH:MM:SS) as a time of day; None stays None."""
    if value is None or isinstance(value, time):
        return value.replace(second=0, microsecond=0) if value else None
    m = re.fullmatch(r"([01]?\d|2[0-3]):([0-5]\d)(?::[0-5]\d)?", str(value).strip())
    if not m:
        raise FoodError("Time eaten must look like 08:10")
    return time(int(m.group(1)), int(m.group(2)))


def default_eaten_at(day: date, today: date, local_now: time | None) -> time | None:
    """When nothing was said: logging today means eating about now; a backfilled day has no time (never invented)."""
    return local_now.replace(second=0, microsecond=0) if day == today and local_now is not None else None


def _check_source(source: str) -> str:
    if source not in SOURCES:
        raise FoodError("Unknown source")
    return source


def _unit_label(d: FoodDish, unit: str | None, by_grams: bool) -> str:
    if by_grams:
        return "g"
    if unit:
        return unit.strip()[:40]
    portions = json.loads(d.portions) if d.portions else []
    return (portions[0]["unit"] if portions else d.unit)[:40]


def _remember(session: Session, d: FoodDish, p: dict, unit: str | None, by_grams: bool, now: datetime) -> None:
    """Keeps the amount just logged as the next default for this dish (joins the caller's transaction)."""
    row = session.get(FoodPortionMemory, d.id)
    prev = None if row is None else {"servings": row.servings, "n": row.n, "streak": row.streak}
    nxt = foodrank.next_memory(prev, round(p["servings"], 4), _unit_label(d, unit, by_grams), None if p["grams"] is None else round(p["grams"], 1))
    if row is None:
        session.add(FoodPortionMemory(dish_id=d.id, updated_at=now, **nxt))
    else:
        for k, v in nxt.items():
            setattr(row, k, v)
        row.updated_at = now


def _dish_entry(session: Session, day: date, meal: str, dish_id: int, servings: float, eating_out: bool, today: date, now: datetime,
                grams: float | None, client_key: str | None, eaten_at: time | None, source: str, unit: str | None = None) -> FoodEntry:
    _check_day(day, today)
    _check_meal(meal)
    _check_source(source)
    d = session.get(FoodDish, dish_id)
    if d is None:
        raise FoodError("Unknown dish")
    p = _portion(d, servings, grams)
    _remember(session, d, p, unit, grams is not None, now)
    return FoodEntry(day=day, meal=meal, dish_id=d.id, name=d.name, servings=p["servings"], kcal=p["kcal"],
                     protein_g=p["protein_g"], carbs_g=p["carbs_g"], fat_g=p["fat_g"], grams=p["grams"],
                     micros=_micros_json(p["micros"]),
                     spread_pct=max(d.spread_pct, OUT_SPREAD) if eating_out else d.spread_pct, logged_at=now, client_key=client_key,
                     eaten_at=eaten_at, source=source)


def log_dish(session: Session, day: date, meal: str, dish_id: int, servings: float, eating_out: bool,
             today: date, now: datetime, grams: float | None = None, client_key: str | None = None,
             eaten_at: time | None = None, source: str = "manual", unit: str | None = None) -> dict:
    """Logs a dish by number of servings, or by grams for dishes that have a weight."""
    entry = _dish_entry(session, day, meal, dish_id, servings, eating_out, today, now, grams, client_key, eaten_at, source, unit)
    return _commit_entry(session, entry, client_key)


def _quick_entry(session: Session, day: date, meal: str, name: str, kcal: float, protein_g: float | None, today: date, now: datetime,
                 carbs_g: float | None, fat_g: float | None, save_dish: bool, client_key: str | None, eaten_at: time | None,
                 source: str) -> tuple[FoodEntry, FoodDish | None]:
    _check_day(day, today)
    _check_meal(meal)
    _check_source(source)
    if not name.strip():
        raise FoodError("Say what it was")
    if not 0 < kcal <= MAX_KCAL:
        raise FoodError(f"Calories must be between 0 and {MAX_KCAL:g}")
    for label, v, cap in (("Protein", protein_g, 500), ("Carbs", carbs_g, 1000), ("Fat", fat_g, 500)):
        if v is not None and not 0 <= v <= cap:
            raise FoodError(f"{label} must be between 0 and {cap} g")
    name = name.strip()[:80]
    dish = None
    if save_dish and session.scalar(select(FoodDish.id).where(FoodDish.name.ilike(name))) is None:
        dish = FoodDish(name=name, unit="1 serving", kcal=kcal, protein_g=protein_g, carbs_g=carbs_g, fat_g=fat_g, spread_pct=OUT_SPREAD,
                        builtin=False, active=True, source="mine", basis="estimate", note="Remembered from a quick entry.", created_at=now)
        session.add(dish)
        session.flush()
    entry = FoodEntry(day=day, meal=meal, dish_id=dish.id if dish else None, name=name, servings=1, kcal=kcal,
                      protein_g=protein_g, carbs_g=carbs_g, fat_g=fat_g, spread_pct=OUT_SPREAD, logged_at=now, client_key=client_key,
                      eaten_at=eaten_at, source=source)
    return entry, dish


def log_quick(session: Session, day: date, meal: str, name: str, kcal: float, protein_g: float | None,
              today: date, now: datetime, carbs_g: float | None = None, fat_g: float | None = None, save_dish: bool = True,
              client_key: str | None = None, eaten_at: time | None = None, source: str = "quick") -> dict:
    """A one-off entry (eating out, something not in the library). Calories required; macros optional and left unknown if
    not given. By default it is also remembered as one of your dishes (one serving) so it can be picked again next time;
    if a dish with that name already exists it is only logged."""
    entry, dish = _quick_entry(session, day, meal, name, kcal, protein_g, today, now, carbs_g, fat_g, save_dish, client_key, eaten_at, source)
    out = _commit_entry(session, entry, client_key)
    return {**out, "saved_dish": dish is not None and not out.get("replayed")}


def entry_for_key(session: Session, client_key: str | None) -> dict | None:
    """The entry an earlier request with this idempotency key created, if any (a retry after a timeout).
    A removed entry is still found, so a late retry never logs it again."""
    if not client_key:
        return None
    e = session.scalar(select(FoodEntry).where(FoodEntry.client_key == client_key))
    return {**entry_dict(e), "replayed": True} if e is not None else None


def _commit_entry(session: Session, entry: FoodEntry, client_key: str | None) -> dict:
    session.add(entry)
    try:
        session.commit()
    except IntegrityError:  # two requests with the same key raced: the other one won
        session.rollback()
        if (existing := entry_for_key(session, client_key)) is None:
            raise
        return existing
    return entry_dict(entry)


# ---- batch: a whole meal in one transaction ----


def log_batch(session: Session, day: date, meal: str, items: list[dict], eating_out: bool, eaten_at: time | None, client_key: str | None,
              source: str | None, today: date, now: datetime) -> dict:
    """Logs every item of a draft meal or none of them. With a `client_key`, item i is stored under "{key}:{i}", so a retry
    (even one that arrives while the first request is still running) returns the entries already written and adds nothing;
    a batch that was only partly written before is completed, not repeated.

    Items: {dish_id, servings|grams, unit?} or {name, kcal, protein_g?, carbs_g?, fat_g?, save_dish?}."""
    if not items:
        raise FoodError("Nothing to log")
    if len(items) > MAX_BATCH_ITEMS:
        raise FoodError(f"A meal logs up to {MAX_BATCH_ITEMS} items at once")
    key = (client_key or "").strip() or None
    if key and len(key) > KEY_MAX:
        raise FoodError(f"The key can be up to {KEY_MAX} characters")
    keys = [f"{key}:{i}" if key else None for i in range(len(items))]
    existing = {e.client_key: e for e in session.scalars(select(FoodEntry).where(FoodEntry.client_key.in_([k for k in keys if k])))} if key else {}
    if key and len(existing) == len(items):
        return _batch_out(keys, existing, [], True)
    when = eaten_at
    made: dict[str, FoodEntry] = dict(existing)
    saved: list[FoodDish] = []
    try:
        for i, it in enumerate(items):
            if keys[i] in existing:
                continue
            try:
                src = source or ("quick" if it.get("dish_id") is None else "manual")
                if it.get("dish_id") is not None:
                    entry = _dish_entry(session, day, meal, it["dish_id"], it.get("servings") or 1.0, eating_out, today, now, it.get("grams"),
                                        keys[i], when, src, it.get("unit"))
                elif it.get("name") and it.get("kcal"):
                    entry, dish = _quick_entry(session, day, meal, it["name"], it["kcal"], it.get("protein_g"), today, now, it.get("carbs_g"),
                                               it.get("fat_g"), it.get("save_dish", False), keys[i], when, src)
                    if dish is not None:
                        saved.append(dish)
                else:
                    raise FoodError("Pick a dish, or give a name and calories")
            except FoodError as exc:
                raise FoodError(f"Item {i + 1}: {exc}") from None
            session.add(entry)
            made[keys[i] or f"#{i}"] = entry
        session.commit()
    except IntegrityError:  # the same key raced in from a second request: its rows won, return them
        session.rollback()
        if not key:
            raise
        got = {e.client_key: e for e in session.scalars(select(FoodEntry).where(FoodEntry.client_key.in_(keys)))}
        if len(got) != len(items):
            raise
        return _batch_out(keys, got, [], True)
    except FoodError:
        session.rollback()
        raise
    ordered = [made[keys[i] or f"#{i}"] for i in range(len(items))]
    return {"entries": [entry_dict(e) for e in ordered if e.deleted_at is None], "replayed": False, "saved_dishes": [dish_dict(d) for d in saved]}


def _batch_out(keys: list, rows: dict[str, FoodEntry], saved: list, replayed: bool) -> dict:
    live = [rows[k] for k in keys if k in rows and rows[k].deleted_at is None]
    return {"entries": [entry_dict(e) for e in live], "replayed": replayed, "saved_dishes": saved}


# ---- remove (soft), restore, purge, bulk ----


def active_entries():
    """The only way to select entries for any total, list, history or copy: removed ones are excluded."""
    return select(FoodEntry).where(FoodEntry.deleted_at.is_(None))


def remove(session: Session, entry_id: int, now: datetime | None = None) -> bool:
    """Soft delete: the entry disappears everywhere but can be restored for a week. False if it is missing or already removed."""
    result = session.execute(update(FoodEntry).where(FoodEntry.id == entry_id, FoodEntry.deleted_at.is_(None))
                             .values(deleted_at=now or utcnow()))
    session.commit()
    return result.rowcount > 0


def restore(session: Session, entry_id: int) -> dict | None:
    e = session.get(FoodEntry, entry_id)
    if e is None:
        return None
    e.deleted_at = None
    session.commit()
    return entry_dict(e)


def purge_deleted(session: Session, now: datetime) -> int:
    """Hard-deletes entries removed more than a week ago. Returns how many."""
    result = session.execute(delete(FoodEntry).where(FoodEntry.deleted_at.is_not(None),
                                                     FoodEntry.deleted_at < now - timedelta(days=PURGE_AFTER_DAYS)))
    session.commit()
    return result.rowcount


def _scale(e: FoodEntry, factor: float) -> None:
    if e.servings * factor > MAX_SERVINGS or e.servings * factor <= 0:
        raise FoodError(f"Servings must be between 0 and {MAX_SERVINGS:g}")
    e.kcal = e.kcal * factor
    for attr in ("protein_g", "carbs_g", "fat_g", "grams"):
        v = getattr(e, attr)
        setattr(e, attr, None if v is None else v * factor)
    e.micros = _micros_json(nutrients.multiply(json.loads(e.micros) if e.micros else None, factor))
    e.servings = e.servings * factor


def bulk(session: Session, ids: list[int], action: str, meal: str | None, scale: float | None, now: datetime) -> dict:
    """Delete, restore, move to a meal, or scale several entries together; all or none."""
    ids = list(dict.fromkeys(ids))
    if not ids or len(ids) > MAX_BULK_IDS:
        raise FoodError(f"Pick between 1 and {MAX_BULK_IDS} entries")
    rows = {e.id: e for e in session.scalars(select(FoodEntry).where(FoodEntry.id.in_(ids)))}
    if len(rows) != len(ids):
        raise FoodError("One of those entries no longer exists")
    if action != "restore" and any(rows[i].deleted_at is not None for i in ids):
        raise FoodError("One of those entries was already removed")
    if action == "delete":
        for e in rows.values():
            e.deleted_at = now
    elif action == "restore":
        for e in rows.values():
            e.deleted_at = None
    elif action == "move":
        _check_meal(meal or "")
        for e in rows.values():
            e.meal = meal
    elif action == "scale":
        if scale is None or not 0 < scale <= MAX_MEAL_SCALE:
            raise FoodError(f"Scale must be between 0 and {MAX_MEAL_SCALE:g}")
        try:
            for e in rows.values():
                _scale(e, scale)
        except FoodError:
            session.rollback()
            raise
    else:
        raise FoodError("Unknown action")
    session.commit()
    return {"entries": [entry_dict(rows[i]) for i in ids], "affected": len(ids)}


def copy_entries(session: Session, source: date, target: date, today: date, now: datetime, meal: str | None = None,
                 target_meal: str | None = None, entry_ids: list[int] | None = None, local_now: time | None = None) -> dict:
    """Copies entries from one day onto another: the whole day, one meal, or chosen entries (`target_meal` puts them in
    another meal, for "same as yesterday's lunch"). Nothing is skipped silently: asking for an entry that is gone is an error."""
    _check_day(target, today)
    if meal is not None:
        _check_meal(meal)
    if target_meal is not None:
        _check_meal(target_meal)
    q = active_entries().where(FoodEntry.day == source).order_by(FoodEntry.id)
    if meal is not None:
        q = q.where(FoodEntry.meal == meal)
    if entry_ids:
        q = q.where(FoodEntry.id.in_(entry_ids))
    rows = list(session.scalars(q))
    if entry_ids and len(rows) != len(set(entry_ids)):
        raise FoodError("One of those entries is gone or isn't from that day")
    eaten = default_eaten_at(target, today, local_now)
    added = []
    for r in rows:
        e = FoodEntry(day=target, meal=target_meal or r.meal, dish_id=r.dish_id, name=r.name, servings=r.servings, kcal=r.kcal,
                      protein_g=r.protein_g, carbs_g=r.carbs_g, fat_g=r.fat_g, grams=r.grams, micros=r.micros,
                      spread_pct=r.spread_pct, logged_at=now, eaten_at=eaten, source="copy")
        session.add(e)
        added.append(e)
    session.commit()
    return {"copied": len(added), "entries": [entry_dict(e) for e in added]}


def copy_day(session: Session, source: date, target: date, today: date, now: datetime) -> int:
    """Copies a day's entries onto another day (typically yesterday onto today). Returns how many were added."""
    return copy_entries(session, source, target, today, now)["copied"]


def entry_dict(e: FoodEntry) -> dict:
    return {"id": e.id, "day": e.day, "meal": e.meal, "dish_id": e.dish_id, "name": e.name, "servings": e.servings,
            "kcal": round(e.kcal), "protein_g": None if e.protein_g is None else round(e.protein_g, 1),
            "carbs_g": None if e.carbs_g is None else round(e.carbs_g, 1),
            "fat_g": None if e.fat_g is None else round(e.fat_g, 1), "spread_pct": e.spread_pct,
            "grams": None if e.grams is None else round(e.grams),
            "micros": json.loads(e.micros) if e.micros else None,
            "eaten_at": None if e.eaten_at is None else e.eaten_at.strftime("%H:%M"), "eaten_at_est": bool(e.eaten_at_est),
            "source": e.source, "deleted_at": e.deleted_at}


def recent_dish_ids(session: Session, limit: int = 12) -> list[int]:
    """The dishes you log most often lately, so the picker can lead with them."""
    since = session.scalar(select(FoodEntry.day).where(FoodEntry.deleted_at.is_(None)).order_by(FoodEntry.day.desc()).limit(1))
    if since is None:
        return []
    rows = session.execute(
        select(FoodEntry.dish_id).where(FoodEntry.dish_id.is_not(None), FoodEntry.deleted_at.is_(None), FoodEntry.day >= since - timedelta(days=30))
    ).scalars()
    counts: dict[int, int] = {}
    for dish_id in rows:
        counts[dish_id] = counts.get(dish_id, 0) + 1
    return [k for k, _ in sorted(counts.items(), key=lambda kv: -kv[1])[:limit]]


def display_time(e: FoodEntry) -> time:
    """When to show an entry in the day's timeline: the time eaten, else a default for its meal. For ordering only."""
    return e.eaten_at or time(*foodrank.MEAL_DEFAULT_TIMES.get(e.meal, (12, 0)))


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
    rows = list(session.scalars(active_entries().where(FoodEntry.day >= since, FoodEntry.day <= day).order_by(FoodEntry.id)))
    by_day: dict[date, list[dict]] = {}
    for r in sorted(rows, key=lambda r: (r.day, display_time(r), r.id)):
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
    return update_entry(session, entry_id, {"servings": servings})


def update_entry(session: Session, entry_id: int, values: dict) -> dict | None:
    """Edits an entry: amount (`servings`, or `grams` for entries that have a weight), `meal`, `eaten_at` (null clears it).
    Amounts scale everything the entry holds. A removed entry can't be edited."""
    e = session.get(FoodEntry, entry_id)
    if e is None or e.deleted_at is not None:
        return None
    if "meal" in values and values["meal"] is not None:
        _check_meal(values["meal"])
    if values.get("servings") is not None and values.get("grams") is not None:
        raise FoodError("Give servings or grams, not both")
    factor = None
    if values.get("servings") is not None:
        if not 0 < values["servings"] <= MAX_SERVINGS:
            raise FoodError(f"Servings must be between 0 and {MAX_SERVINGS:g}")
        factor = values["servings"] / e.servings
    elif values.get("grams") is not None:
        if not e.grams:
            raise FoodError("This entry is logged by serving, not by grams")
        if not 0 < values["grams"] <= MAX_LOG_GRAMS:
            raise FoodError(f"Grams must be between 0 and {MAX_LOG_GRAMS:g}")
        factor = values["grams"] / e.grams
    if factor is not None:
        try:
            _scale(e, factor)
        except FoodError:
            session.rollback()
            raise
    if values.get("meal") is not None:
        e.meal = values["meal"]
    if "eaten_at" in values:
        e.eaten_at, e.eaten_at_est = parse_eaten_at(values["eaten_at"]), False
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
            "last_used": m.last_used, "pinned": bool(m.pinned)}


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
    by_id = {e.id: e for e in session.scalars(active_entries().where(FoodEntry.id.in_(entry_ids)))}
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


def update_meal(session: Session, meal_id: int, values: dict) -> dict | None:
    """Renames and/or pins a saved meal."""
    m = session.get(FoodMeal, meal_id)
    if m is None:
        return None
    if values.get("name") is not None:
        name = values["name"].strip()[:80]
        if not name:
            raise FoodError("Give the meal a name")
        if session.scalar(select(FoodMeal.id).where(FoodMeal.name.ilike(name), FoodMeal.id != meal_id)) is not None:
            raise FoodError("You already have a meal with that name")
        m.name = name
    if values.get("pinned") is not None:
        m.pinned = bool(values["pinned"])
    session.commit()
    return meal_dict(session, m)


def delete_meal(session: Session, meal_id: int) -> bool:
    session.execute(delete(FoodMealItem).where(FoodMealItem.meal_id == meal_id))
    result = session.execute(delete(FoodMeal).where(FoodMeal.id == meal_id))
    session.commit()
    return result.rowcount > 0


def log_meal(session: Session, meal_id: int, day: date, meal: str, scale: float, eating_out: bool, today: date, now: datetime,
             eaten_at: time | None = None) -> list[dict]:
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
                          spread_pct=max(spread, OUT_SPREAD) if eating_out else spread, logged_at=now, eaten_at=eaten_at, source="chip")
        session.add(entry)
        added.append(entry)
    m.last_used = now
    session.commit()
    return [entry_dict(e) for e in added]
