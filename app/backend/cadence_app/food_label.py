"""Reads a printed nutrition table from OCR text. Pure: text in, a reviewable result out; nothing is saved here.

Labels differ, so the reader does not guess silently:
- Columns come from the header ("per 100 g", "per serve (30 g)", "per pack"). A row with two numbers is read in header
  order; a third number such as %RDA / %NRV is ignored. With no header, one number is taken as per 100 g and two numbers as
  per 100 g then per serve, and the result says the column was assumed.
- Energy prefers kcal. A value tagged kJ is converted (÷ 4.184); an untagged value above 900 in the first column is read as
  kJ. Salt is converted to sodium (salt g × 400 = sodium mg).
- Anything not found is left out (unknown), never zero. Each column carries the same plausibility checks as the catalogue
  builder (macros that cannot add up to the calories, more than 100 g of nutrients in 100 g), so a misread digit is flagged
  for the person reviewing the photo beside the fields.
OCR misreads digits now and then; the numbers are a starting point to confirm, not a measurement.
"""

from __future__ import annotations

import re

COLUMNS = ("per_100g", "per_serving")
KJ_PER_KCAL = 4.184
SODIUM_MG_PER_SALT_G = 400.0
MACRO_TOLERANCE, MACRO_SLACK_KCAL = 0.40, 15.0

NUMBER = re.compile(r"(?<![\w.])(\d+(?:\.\d+)?)\s*(kcal|kj|mg|µg|mcg|ug|g|ml)?(?!\s*%)(?![\w])", re.IGNORECASE)
HEADER_100 = re.compile(r"(?:per\s*)?100\s*(?:g|gm|gram|grams|ml)\b", re.IGNORECASE)
HEADER_SERVE = re.compile(r"(?:per\s*)?(?:serve|serving|portion|pack|bar|piece|sachet)\b", re.IGNORECASE)
SERVING_SIZE = [
    re.compile(r"serv(?:e|ing)?\s*(?:size|weight)?\s*[:\-=]?\s*\(?\s*(\d+(?:\.\d+)?)\s*(g|gm|ml)\b", re.IGNORECASE),
    re.compile(r"(?:per\s*)?(?:serve|serving|portion|pack|bar)\s*\(?\s*(\d+(?:\.\d+)?)\s*(g|gm|ml)\b", re.IGNORECASE),
    re.compile(r"\(\s*(\d+(?:\.\d+)?)\s*(g|gm|ml)\s*\)", re.IGNORECASE),
]

# key, label pattern. Checked in order, so "saturated fat" is not read as "fat".
ROWS: tuple[tuple[str, re.Pattern], ...] = (
    ("energy", re.compile(r"^\W*(energy|calories|calorie)\b", re.IGNORECASE)),
    ("protein", re.compile(r"^\W*proteins?\b", re.IGNORECASE)),
    ("sat_fat_g", re.compile(r"^\W*(of which\s*)?(saturated|saturates|sat\.?\s*fat)", re.IGNORECASE)),
    ("skip", re.compile(r"^\W*(trans|mono|poly|added\s*sugar|cholesterol|of which\s*added)", re.IGNORECASE)),
    ("sugars_g", re.compile(r"^\W*(of which\s*)?(total\s*)?sugars?\b", re.IGNORECASE)),
    ("carbs_g", re.compile(r"^\W*(total\s*)?(carbohydrates?|carbs)\b", re.IGNORECASE)),
    ("fat_g", re.compile(r"^\W*(total\s*)?fats?\b", re.IGNORECASE)),
    ("fibre_g", re.compile(r"^\W*(dietary\s*)?fib(re|er)s?\b", re.IGNORECASE)),
    ("sodium", re.compile(r"^\W*sodium\b", re.IGNORECASE)),
    ("salt", re.compile(r"^\W*salt\b", re.IGNORECASE)),
)
OUT_KEYS = ("kcal", "protein_g", "carbs_g", "fat_g", "sugars_g", "sat_fat_g", "fibre_g", "sodium_mg")


def _clean(text: str) -> list[str]:
    lines = []
    for raw in text.replace(" ", " ").splitlines():
        line = re.sub(r"(?<=\d),(?=\d{1,2}\b)", ".", raw.strip())  # 3,5 -> 3.5
        line = re.sub(r"[|_]+", " ", line)
        if line:
            lines.append(line)
    return lines


def _numbers(rest: str) -> list[tuple[float, str]]:
    return [(float(m.group(1)), (m.group(2) or "").lower()) for m in NUMBER.finditer(rest)]


def _columns(lines: list[str], first_row: int) -> list[str]:
    """Column order from the header lines above the first nutrient row."""
    found: list[tuple[int, str]] = []
    offset = 0
    for line in lines[:first_row]:
        m100, ms = HEADER_100.search(line), HEADER_SERVE.search(line)
        if m100:
            found.append((offset + m100.start(), "per_100g"))
        if ms:
            found.append((offset + ms.start(), "per_serving"))
        offset += len(line) + 1
    order: list[str] = []
    for _, key in sorted(found):
        if key not in order:
            order.append(key)
    return order


def serving_size(lines: list[str]) -> tuple[float | None, str | None]:
    for line in lines:
        for pattern in SERVING_SIZE:
            m = pattern.search(line)
            if m and 0 < float(m.group(1)) <= 3000:
                return float(m.group(1)), m.group(2).lower().replace("gm", "g")
    return None, None


def _energy(nums: list[tuple[float, str]], label: str, want: int, warnings: list[str]) -> list[float]:
    kcal = [v for v, u in nums if u == "kcal"]
    if kcal:
        return kcal[:want]
    kj = [v for v, u in nums if u == "kj"]
    if kj:
        return [round(v / KJ_PER_KCAL) for v in kj[:want]]
    plain = [v for v, u in nums if u == ""]
    if "kj" in label.lower() and "kcal" not in label.lower():
        return [round(v / KJ_PER_KCAL) for v in plain[:want]]
    if plain and "kcal" not in label.lower() and "cal" not in label.lower() and plain[0] > 900:
        warnings.append("Energy looked like kilojoules and was converted; check it.")
        return [round(v / KJ_PER_KCAL) for v in plain[:want]]
    return plain[:want]


def _value(key: str, nums: list[tuple[float, str]], want: int) -> list[float]:
    plain = [(v, u) for v, u in nums if u not in ("kcal", "kj")]
    values = []
    for v, u in plain[:want]:
        if key == "sodium" and u == "g":
            v *= 1000
        if key == "salt" and u == "mg":
            v /= 1000
        values.append(v)
    return values


def issues(values: dict, per_100g: bool) -> list[str]:
    """Why this column's numbers can't all be right (same rules as the catalogue builder), or an empty list."""
    kcal, p, c, f = (values.get(k) for k in ("kcal", "protein_g", "carbs_g", "fat_g"))
    out = []
    if per_100g and kcal is not None and not 0 <= kcal <= 900:
        out.append("Calories per 100 g are above 900, which no food reaches; one digit may be misread.")
    if per_100g and sum(v for v in (p, c, f) if v is not None) > 101:
        out.append("More than 100 g of protein, carbs and fat in 100 g; a number may be misread.")
    if kcal is not None and None not in (p, c, f):
        estimated = 4 * p + 4 * c + 9 * f
        if abs(kcal - estimated) > MACRO_TOLERANCE * max(kcal, estimated) + MACRO_SLACK_KCAL:
            out.append(f"The macros add up to about {round(estimated)} kcal but the label says {round(kcal)}; check the numbers.")
    return out


def parse(text: str) -> dict:
    """{columns: {per_100g|per_serving: {kcal, protein_g, ...}}, order, serving_g, serving_unit, column_assumed, warnings, issues}."""
    lines = _clean(text)
    kinds = [next((k for k, pat in ROWS if pat.search(line)), None) for line in lines]
    first = next((i for i, k in enumerate(kinds) if k and k != "skip"), len(lines))
    order = _columns(lines, first)
    serving_g, serving_unit = serving_size(lines[: first + 1] + lines)
    warnings: list[str] = []
    assumed = False
    parsed: dict[str, dict[str, list[float]]] = {}
    for line, kind in zip(lines, kinds):
        if not kind or kind == "skip":
            continue
        label_end = re.search(r"[\d(]", line)
        label = line[: label_end.start()] if label_end else line
        nums = _numbers(line[len(label):] if label_end else "")
        if not nums:
            continue
        want = len(order) or 2
        if kind == "energy":
            vals = _energy(nums, line, want, warnings)
        else:
            vals = _value(kind, nums, want)
        if vals and kind not in parsed:
            parsed[kind] = {"vals": vals}
    if not order:
        counts = [len(p["vals"]) for p in parsed.values()]
        order = ["per_100g", "per_serving"][: max(counts, default=1) if max(counts, default=1) <= 2 else 2]
        assumed = bool(parsed)
        if assumed:
            warnings.append("The label's column headings weren't read, so the first column is taken as per 100 g.")
    columns: dict[str, dict[str, float]] = {k: {} for k in order}
    for kind, p in parsed.items():
        vals = p["vals"]
        for idx, col in enumerate(order[: len(vals)]):
            v = vals[idx]
            if kind == "energy":
                columns[col]["kcal"] = float(v)
            elif kind == "protein":
                columns[col]["protein_g"] = v
            elif kind == "salt":
                columns[col].setdefault("sodium_mg", round(v * SODIUM_MG_PER_SALT_G))
            elif kind == "sodium":
                columns[col]["sodium_mg"] = v
            else:
                columns[col][kind] = v
    columns = {k: v for k, v in columns.items() if v}
    found_issues = {k: issues(v, k == "per_100g") for k, v in columns.items()}
    if not columns:
        warnings.append("No nutrition table was found in the text. Try a flatter, closer photo, or enter the numbers by hand.")
    for col, v in columns.items():
        if "kcal" not in v:
            warnings.append(f"No calories were read for the {col.replace('_', ' ')} column.")
    return {"columns": columns, "order": [k for k in order if k in columns], "serving_g": serving_g, "serving_unit": serving_unit,
            "column_assumed": assumed, "warnings": list(dict.fromkeys(warnings)), "issues": found_issues}
