"""The micronutrients the food log tracks, taken from the per-100 g nutrient table of each catalogue dish.

Only nutrients that most pages carry are kept. A page without a value is missing data, not zero: a day total says how
many of its foods reported the nutrient, and a nutrient no food reported is shown as unknown.

Reference amounts are for context, not a personal prescription or medical advice:
- fibre ≥ 25 g, sodium < 2,000 mg, potassium ≥ 3,510 mg: WHO guidelines for adults (fibre 2023, sodium 2012, potassium 2012).
- everything else: US FDA Daily Values (21 CFR 101.9, 2020 label update), a labelling reference for a 2,000 kcal diet.
Total sugars include sugar in fruit and milk, so they carry no limit here.
"""

from __future__ import annotations

# key, label, unit, name in the source nutrient table, reference amount, kind ("target" to reach, "limit" to stay under, None)
MICROS: tuple[tuple[str, str, str, str, float | None, str | None, str], ...] = (
    ("fibre_g", "Fibre", "g", "Fibre", 25, "target", "WHO"),
    ("sugars_g", "Sugars", "g", "Sugars", None, None, ""),
    ("sat_fat_g", "Saturated fat", "g", "Saturated fat", 20, "limit", "FDA Daily Value"),
    ("sodium_mg", "Sodium", "mg", "Sodium", 2000, "limit", "WHO"),
    ("potassium_mg", "Potassium", "mg", "Potassium", 3510, "target", "WHO"),
    ("calcium_mg", "Calcium", "mg", "Calcium", 1300, "target", "FDA Daily Value"),
    ("iron_mg", "Iron", "mg", "Iron", 18, "target", "FDA Daily Value"),
    ("magnesium_mg", "Magnesium", "mg", "Magnesium", 420, "target", "FDA Daily Value"),
    ("zinc_mg", "Zinc", "mg", "Zinc", 11, "target", "FDA Daily Value"),
    ("vitamin_c_mg", "Vitamin C", "mg", "Vitamin C", 90, "target", "FDA Daily Value"),
    ("vitamin_a_ug", "Vitamin A", "µg", "Vitamin A", 900, "target", "FDA Daily Value"),
)
KEYS = tuple(m[0] for m in MICROS)
_UNIT = {"g": "g", "mg": "mg", "ug": "µg", "µg": "µg"}


def pick(table: dict | None) -> dict[str, float]:
    """Per-100 g amounts for the tracked nutrients from a page's `{name: [value, unit]}` table; absent ones are left out."""
    out: dict[str, float] = {}
    for key, _label, unit, name, _ref, _kind, _src in MICROS:
        got = (table or {}).get(name)
        if not got or got[0] is None or _UNIT.get(got[1]) != unit or got[0] < 0:
            continue
        out[key] = round(float(got[0]), 2)
    return out


def scale(per100: dict[str, float] | None, grams: float | None) -> dict[str, float] | None:
    """Amounts in `grams` of food, or None when the food has no nutrient table or no known weight."""
    if not per100 or not grams:
        return None
    return {k: round(v * grams / 100, 2) for k, v in per100.items()}


def multiply(micros: dict[str, float] | None, factor: float) -> dict[str, float] | None:
    return {k: round(v * factor, 2) for k, v in micros.items()} if micros else micros


def summarise(entry_micros: list[dict[str, float] | None]) -> list[dict]:
    """Day totals for each nutrient with how many of the day's foods reported it. `[]` when nothing is logged."""
    if not entry_micros:
        return []
    rows = []
    for key, label, unit, _name, ref, kind, source in MICROS:
        have = [m[key] for m in entry_micros if m and key in m]
        amount = round(sum(have), 1) if have else None
        rows.append({
            "key": key, "label": label, "unit": unit, "amount": amount, "foods_with": len(have), "foods": len(entry_micros),
            "reference": ref, "kind": kind, "source": source,
            "pct": None if amount is None or not ref else round(amount / ref * 100),
        })
    return rows
