"""Builds the food catalogue from the private `food-data` submodule (a personal-use crawl of the food library).

    python -m cadence_app.food_import [path/to/food-data]

reads `library/nutrifacts.jsonl` and writes `library/catalogue.json` plus `library/catalogue_report.json`
beside it. The app loads the catalogue on start. No food data lives in this repository.

What the source is: the source site publishes nutrition per 100 g with named portions (katori, piece, cup, with grams).
Its numbers are calculated from recipes taken from the web (each page names its source, such as a recipe site) and are
marked unverified, so every dish keeps that source and the app shows it. Estimates, not measurements.

Cleaning rules
- Nutrition is per 100 g as eaten; a portion is a weight, so per-serving = per 100 g x grams / 100. Every unit label
  states its grams.
- Pages that are the same food under different names (identical nutrient tables, e.g. "Aam"/"Mango") become one dish with
  the other names kept as search aliases. Different foods that share a name keep it plus a short code.
- Rows that can't be right are dropped and counted: energy above 900 kcal per 100 g, more than 100 g of nutrients in
  100 g, or macros that disagree with calories by more than 40% (+15 kcal).
- Non-Latin names are kept as aliases only, never as the dish name.
- A dish's `ref_code` is a hash of its nutrient table, so it never changes as the crawl adds pages; `page_codes` lists the
  the source site pages behind it, which lets the app recognise a dish it stored under an earlier code.
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path

MAX_KCAL_100G = 900.0
MAX_MACRO_MASS_100G = 101.0
MACRO_TOLERANCE = 0.40
MACRO_SLACK_KCAL = 15.0
MAX_PORTIONS = 8
SPREAD_UNVERIFIED, SPREAD_VERIFIED = 25, 15
# Portion names that are not household measures of the food itself.
SKIP_PORTION_UNITS = {"oz", "g", "gram", "grams", "ml", "serve"}


def _ascii(s: str | None) -> bool:
    return bool(s) and s.isascii()


def _clean_name(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()[:80]


def _code(record_id: str) -> str:
    """The page's trailing 10-hex hash: short, unique, and stable across crawls."""
    return record_id.rsplit("-", 1)[-1][:24]


def _dish_code(fingerprint: str) -> str:
    """A dish's identity is its nutrient table, so the code survives later pages joining the group or taking over its name."""
    return hashlib.sha1(fingerprint.encode()).hexdigest()[:10]


def _fingerprint(r: dict) -> str:
    p = r["per_100g"]
    table = sorted((k, v[0]) for k, v in (r.get("nutrients_per_100g") or {}).items())
    return json.dumps([p["kcal"], p["protein_g"], p["carbs_g"], p["fat_g"], p.get("fibre_g"), table], sort_keys=True)


def check(per100: dict) -> str | None:
    """Why a per-100 g row can't be right, or None."""
    kcal, p, c, f = (per100.get(k) or 0.0 for k in ("kcal", "protein_g", "carbs_g", "fat_g"))
    if per100.get("kcal") is None:
        return "no calories"
    if not 0 <= kcal <= MAX_KCAL_100G:
        return "calories out of range"
    if p + c + f > MAX_MACRO_MASS_100G:
        return "more nutrient than food"
    est = 4 * p + 4 * c + 9 * f
    if abs(est - kcal) > MACRO_TOLERANCE * max(kcal, est) + MACRO_SLACK_KCAL:
        return "macros disagree with calories"
    return None


def portions_of(r: dict) -> list[dict]:
    """Household portions with their weights, default first, no duplicates."""
    out, seen = [], set()
    dflt = r.get("default_serving")
    candidates = ([dflt] if dflt else []) + list(r.get("portions") or [])
    for c in candidates:
        unit, grams = (c.get("unit") or "").strip(), c.get("grams")
        if not unit or not grams or grams <= 1 or unit.lower() in SKIP_PORTION_UNITS:
            continue
        key = (unit.lower(), round(grams, 1))
        if key in seen:
            continue
        seen.add(key)
        out.append({"unit": unit, "grams": round(float(grams), 1)})
    return out[:MAX_PORTIONS]


def _source_note(r: dict) -> str:
    domains = (r.get("provenance") or {}).get("labels") or []
    where = f"a recipe from {domains[0]}" if domains else "a recipe in its database"
    state = "verified by the source site" if r.get("verified") else "not verified"
    return f"the source site: calculated from {where}; {state}."[:240]


def _rank(r: dict) -> tuple:
    """Best record to name a group of identical foods: Latin name, a real household portion, a fuller table, short name."""
    return (not _ascii(r.get("name")), not portions_of(r), -len(r.get("nutrients_per_100g") or {}), len(r.get("name") or ""))


def dish_from(group: list[dict]) -> dict:
    group = sorted(group, key=_rank)
    best = group[0]
    per = best["per_100g"]
    portions = portions_of(best)
    if portions:
        unit_g, label = portions[0]["grams"], f'1 {portions[0]["unit"]} (≈{portions[0]["grams"]:g} g)'
    else:
        unit_g, label = 100.0, "100 g"
    per100 = {k: round(per.get(k) or 0.0, 2) for k in ("kcal", "protein_g", "carbs_g", "fat_g")}
    aliases, seen = [], set()
    for r in group[1:] + group[:1]:
        n = _clean_name(r.get("name") or "")
        if n and n.lower() != _clean_name(best["name"]).lower() and n.lower() not in seen:
            seen.add(n.lower())
            aliases.append(n)
    return {
        "name": _clean_name(best["name"]), "unit": label, "grams": unit_g, "per_100g": per100, "portions": portions,
        "kcal": round(per100["kcal"] * unit_g / 100, 1), "protein_g": round(per100["protein_g"] * unit_g / 100, 1),
        "carbs_g": round(per100["carbs_g"] * unit_g / 100, 1), "fat_g": round(per100["fat_g"] * unit_g / 100, 1),
        "spread_pct": SPREAD_VERIFIED if best.get("verified") else SPREAD_UNVERIFIED,
        "basis": "library", "source": "library", "ref_code": _dish_code(_fingerprint(best)),
        "page_codes": sorted(_code(r["id"]) for r in group), "note": _source_note(best),
        "aliases": aliases,
    }


def build_catalogue(records: list[dict]) -> tuple[list[dict], dict]:
    dropped: dict[str, int] = {}
    groups: dict[str, list[dict]] = {}
    for r in records:
        if not r.get("per_100g") or not _clean_name(r.get("name") or ""):
            dropped["no data or name"] = dropped.get("no data or name", 0) + 1
            continue
        why = check(r["per_100g"])
        if why:
            dropped[why] = dropped.get(why, 0) + 1
            continue
        groups.setdefault(_fingerprint(r), []).append(r)
    dishes, no_latin_name = [], 0
    for group in groups.values():
        if not any(_ascii(r.get("name")) for r in group):
            no_latin_name += 1
            continue
        dishes.append(dish_from(group))
    # The library needs every name unique as written; different foods that share a name get their code appended.
    count: dict[str, int] = {}
    for d in dishes:
        count[d["name"].lower()] = count.get(d["name"].lower(), 0) + 1
    for d in dishes:
        if count[d["name"].lower()] > 1:
            d["name"] = f'{d["name"][:70]} ({d["ref_code"][:4]})'
    dishes.sort(key=lambda d: d["name"].lower())
    report = {
        "pages": len(records), "dishes": len(dishes), "dropped": dropped, "skipped_no_latin_name": no_latin_name,
        "merged_alias_pages": len(records) - sum(dropped.values()) - no_latin_name - len(dishes),
        "with_household_portion": sum(1 for d in dishes if d["portions"]),
        "unverified": sum(1 for d in dishes if d["spread_pct"] == SPREAD_UNVERIFIED),
    }
    return dishes, report


def build(food_data: Path) -> dict:
    src = food_data / "library" / "nutrifacts.jsonl"
    records = [json.loads(line) for line in src.read_text(encoding="utf-8").splitlines() if line.strip()]
    dishes, report = build_catalogue(records)
    out = food_data / "library"
    for name, text in (("catalogue.json", json.dumps({"dishes": dishes}, ensure_ascii=False)), ("catalogue_report.json", json.dumps(report, indent=1, ensure_ascii=False))):
        tmp = out / (name + ".tmp")
        tmp.write_text(text + "\n", encoding="utf-8")
        tmp.replace(out / name)  # the running service never sees a half-written catalogue
    return report


if __name__ == "__main__":
    from cadence_app.config import REPO_ROOT

    print(json.dumps(build(Path(sys.argv[1]) if len(sys.argv) > 1 else REPO_ROOT / "food-data"), indent=1))
