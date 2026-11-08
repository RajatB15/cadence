"""Improve, part 6: population benchmarks as grey context, never as pass/fail (pure).

Bands come from published age/sex tables (Liguori 2021 ACSM/Cooper; Kaminsky 2015 FRIEND; Ostchega 2011 NHANES for
resting HR; Nunan 2010 for HRV) keyed by source id in improve_sources.py. Only tables that were checked against the
primary source are bundled; inventing values would present guesses as norms.

Bundled: resting heart rate from Ostchega 2011 (source key `ostchega2011`), National Health Statistics Reports no. 41,
Tables 2 (males) and 3 (females), https://www.cdc.gov/nchs/data/nhsr/nhsr041.pdf. Population: US NHANES 1999-2008, people
without a medical condition or medication affecting pulse; pulse taken seated after ~4 minutes of quiet rest by a
clinician, in beats/min. A wearable's resting HR (lowest sustained reading, usually asleep) is not the same measurement
and typically reads lower, so the band is context, not a verdict. Cut points are the published 10th/25th/75th/90th
percentiles (integers as printed), age groups 20-39, 40-59, 60-79, 80+ (the report has no finer adult groups).

NOT bundled (could not be verified from the primary source, so `band` stays null):
- VO2max: Kaminsky 2022 FRIEND treadmill percentiles (Mayo Clin Proc 97(2):285-293, Table 3, key `kaminsky2022`). The
  publisher full text was inaccessible and secondary sites disagree. Garmin's VO2max is a watch estimate, not a
  treadmill test, so even with the table it would be a rough comparison.
- HRV: no verified population table; HRV is shown against the personal baseline only (very wide, age dependent).
`band_for` and the monotonic/boundary checks are tested with a synthetic table.
"""

from __future__ import annotations

# metric -> sex -> [(age_from, age_to, [cut points ascending], [labels one longer than the cuts])]
_RHR_LABELS = ["Below the 10th percentile", "10th to 25th percentile", "Middle half (25th to 75th)", "75th to 90th percentile", "Above the 90th percentile"]
TABLES: dict[str, dict] = {
    "resting_hr": {  # Ostchega 2011, NHSR 41, Table 2 (male) / Table 3 (female): [10th, 25th, 75th, 90th] percentiles, bpm
        "male": [(20, 39, [55.0, 61.0, 76.0, 84.0], _RHR_LABELS), (40, 59, [55.0, 61.0, 77.0, 85.0], _RHR_LABELS),
                 (60, 79, [54.0, 60.0, 75.0, 84.0], _RHR_LABELS), (80, 130, [54.0, 61.0, 78.0, 86.0], _RHR_LABELS)],
        "female": [(20, 39, [60.0, 66.0, 82.0, 89.0], _RHR_LABELS), (40, 59, [59.0, 64.0, 79.0, 86.0], _RHR_LABELS),
                   (60, 79, [59.0, 64.0, 78.0, 86.0], _RHR_LABELS), (80, 130, [59.0, 64.0, 77.0, 85.0], _RHR_LABELS)],
    },
}
CAVEATS = {
    "vo2max": "Garmin's VO2max is a watch estimate, not a lab treadmill test, so it can differ from published norms.",
    "resting_hr": "Published values are a seated clinic pulse after about 4 minutes of rest (US NHANES 1999-2008); a watch's resting HR is measured differently and usually reads lower. Context, not a verdict.",
    "hrv": "No population reference is bundled: HRV varies widely between people and with age, so compare with your own baseline.",
}
SOURCES = {"vo2max": "liguori2021", "resting_hr": "ostchega2011", "hrv": "nunan2010"}


def band_for(table: dict, metric: str, sex: str, age: float, value: float) -> str | None:
    for lo, hi, cuts, labels in table.get(metric, {}).get(sex, []):
        if lo <= age <= hi:
            return labels[sum(1 for c in cuts if value >= c)]
    return None


def monotonic(table: dict) -> bool:
    """Cut points rise within an age group (checked by tests whenever a table is added)."""
    return all(list(cuts) == sorted(cuts) and len(labels) == len(cuts) + 1
               for sexes in table.values() for rows in sexes.values() for _, _, cuts, labels in rows)


def benchmarks(baselines: dict[str, dict | None], vo2_value: float | None, profile: dict | None, age: float | None, tables: dict | None = None) -> dict:
    tables = TABLES if tables is None else tables
    missing = profile is None or age is None
    out: dict = {"profile_missing": missing}
    if vo2_value is not None:
        band = None if missing else band_for(tables, "vo2max", profile["sex"], age, vo2_value)
        out["vo2max"] = {"value": round(vo2_value, 1), "band": band, "percentile": None, "source": SOURCES["vo2max"], "estimate": True, "caveat": CAVEATS["vo2max"]}
    for m in ("resting_hr", "hrv"):
        b = baselines.get(m)
        if b:
            band = None if missing else band_for(tables, m, profile["sex"], age, b["mean"])
            out[m] = {"value": b["mean"], "band": band, "personal_band": b["band"], "percentile": None, "source": SOURCES[m], "estimate": False, "caveat": CAVEATS[m]}
    return out
