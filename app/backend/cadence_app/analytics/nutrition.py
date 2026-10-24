"""Nutrition targets and energy balance from your food log, weight trend, goal and Garmin energy burn.

Pure algorithms: `food_plan` takes plain numbers and returns plain dicts. Loading lives in `foodlog.plan_inputs`, wording
in `notes.nutrition`. Everything is a range with its sample size, and nothing here is medical advice or a prescription.

Sources
- Protein 1.6-2.2 g/kg/day: Morton et al. (2018), Br J Sports Med 52(6):376-384 (gains in fat-free mass level off near
  1.6 g/kg/day); Iraki, Fitschen, Espinar & Helms (2019), Sports 7(7):154 (1.6-2.2 g/kg/day, 0.40-0.55 g/kg per meal over
  3-6 meals, fat 0.5-1.5 g/kg/day).
- Rate of loss 0.5-1% of body weight per week to protect muscle: Helms, Aragon & Fitschen (2014), J Int Soc Sports Nutr
  11:20. Energy surplus about 10-20% for novice/intermediate lifters, aiming at 0.25-0.5% of body weight per week:
  Iraki et al. (2019); advanced lifters should be more conservative.
- 7,700 kcal per kg of body weight change is a rough rule of thumb only. Hall et al. (2011), Lancet 378:826-837, show
  it overestimates long-run change because expenditure shifts as weight does; so anything built on it here is shown as a
  range and only over a few weeks.
- Reference energy use: the mean of Garmin's daily total-calories estimate (a wrist-worn estimate, treated as +-10%),
  or, before there is a week of it, the Mifflin-St Jeor x activity estimate from `analytics/body.py` (+-10%).

Minimum data: a day is "logged" if it has an entry; weekly averages need 4 logged days; the intake-plus-weight-trend
estimate of your real expenditure needs 10 logged days in the last 14 and a weight trend. Missing is never zero.
"""

from __future__ import annotations

from datetime import date, timedelta

KCAL_PER_KG = 7700.0
PROTEIN_G_PER_KG = (1.6, 2.2)
FAT_G_PER_KG = (0.5, 1.5)
PROTEIN_PER_MEAL_G_PER_KG = (0.40, 0.55)
LOSS_PCT_WEEK = (0.5, 1.0)
GAIN_PCT_WEEK = (0.25, 0.5)
SURPLUS_PCT = (10, 20)
MAINTAIN_PCT = 5
MAX_DEFICIT_PCT = 25  # of reference energy; the pace guide never asks for more than this
PHASE_DEADBAND_KG = 0.5
MIN_BURN_DAYS = 7
BURN_WINDOW_DAYS = 14
WATCH_ERROR = 0.10  # +-10% on a wrist-worn energy estimate; the formula estimate gets the same
MIN_LOGGED_FOR_BALANCE = 4
MIN_LOGGED_FOR_IMPLIED = 10
IMPLIED_WINDOW_DAYS = 14


def phase(weight_kg: float | None, goal_kg: float | None) -> str:
    """cut / gain / maintain from the weight goal. A weight goal cannot tell muscle from fat, so 'gain' is only a direction."""
    if weight_kg is None or goal_kg is None or abs(goal_kg - weight_kg) < PHASE_DEADBAND_KG:
        return "maintain"
    return "cut" if goal_kg < weight_kg else "gain"


def reference_energy(burn_by_day: dict[date, float], today: date, formula_active_kcal: float | None) -> dict | None:
    """What a typical day costs: Garmin's recent mean when there are enough days, else the formula estimate."""
    recent = [v for d, v in burn_by_day.items() if 0 < (today - d).days <= BURN_WINDOW_DAYS and v and v > 0]
    if len(recent) >= MIN_BURN_DAYS:
        mean = sum(recent) / len(recent)
        return {"kcal": round(mean), "low": round(mean * (1 - WATCH_ERROR)), "high": round(mean * (1 + WATCH_ERROR)),
                "source": "garmin", "days": len(recent)}
    if formula_active_kcal:
        k = formula_active_kcal
        return {"kcal": round(k), "low": round(k * (1 - WATCH_ERROR)), "high": round(k * (1 + WATCH_ERROR)), "source": "formula", "days": 0}
    return None


def targets(ph: str, weight_kg: float, reference: dict | None, bmr_kcal: float | None) -> dict:
    """Daily ranges for energy, protein and fat plus a weekly pace guide, for the current phase."""
    out: dict = {
        "phase": ph,
        "protein_g": [round(weight_kg * x) for x in PROTEIN_G_PER_KG],
        "protein_per_meal_g": [round(weight_kg * x) for x in PROTEIN_PER_MEAL_G_PER_KG],
        "fat_g": [round(weight_kg * x) for x in FAT_G_PER_KG],
        "kcal": None, "pace_pct_week": None, "pace_kg_week": None,
    }
    if ph == "cut":
        out["pace_pct_week"] = list(LOSS_PCT_WEEK)
    elif ph == "gain":
        out["pace_pct_week"] = list(GAIN_PCT_WEEK)
    if out["pace_pct_week"]:
        out["pace_kg_week"] = [round(weight_kg * p / 100, 2) for p in out["pace_pct_week"]]
    if reference is None:
        return out
    e = reference["kcal"]
    if ph == "cut":
        gentle, firm = (weight_kg * p / 100 * KCAL_PER_KG / 7 for p in LOSS_PCT_WEEK)
        firm = min(firm, e * MAX_DEFICIT_PCT / 100)
        lo, hi = e - firm, e - gentle
    elif ph == "gain":
        lo, hi = e * (1 + SURPLUS_PCT[0] / 100), e * (1 + SURPLUS_PCT[1] / 100)
    else:
        lo, hi = e * (1 - MAINTAIN_PCT / 100), e * (1 + MAINTAIN_PCT / 100)
    if bmr_kcal:
        lo, hi = max(lo, bmr_kcal), max(hi, bmr_kcal)  # never aim below resting energy
    out["kcal"] = [round(lo / 10) * 10, round(hi / 10) * 10]
    return out


def day_status(summary: dict, target_kcal: list[int] | None) -> dict:
    """Where a day's logged calories sit against the target range. Compares ranges, so an uncertain day isn't called over/under."""
    if not summary["logged"]:
        return {"state": "not_logged"}
    if target_kcal is None:
        return {"state": "no_target"}
    lo, hi = target_kcal
    state = "under" if summary["kcal_high"] < lo else "over" if summary["kcal_low"] > hi else "within"
    return {"state": state, "remaining_kcal": [max(0, lo - summary["kcal_high"]), max(0, hi - summary["kcal_low"])]}


def meal_protein(entries: list[dict]) -> dict[str, float]:
    """Protein logged per meal; meals without protein figures are left out rather than counted as zero."""
    out: dict[str, float] = {}
    for e in entries:
        if e.get("protein_g") is not None:
            out[e["meal"]] = round(out.get(e["meal"], 0.0) + e["protein_g"], 1)
    return out


def balance(trail: list[dict], burn_by_day: dict[date, float]) -> dict | None:
    """Mean logged intake against Garmin's burn on the same days, as a range. None until 4 logged days with a burn figure."""
    rows = [(t, burn_by_day.get(t["day"])) for t in trail if t["logged"]]
    rows = [(t, b) for t, b in rows if b]
    if len(rows) < MIN_LOGGED_FOR_BALANCE:
        return None
    n = len(rows)
    intake = sum(t["kcal"] for t, _ in rows) / n
    low = sum(t["kcal_low"] for t, _ in rows) / n
    high = sum(t["kcal_high"] for t, _ in rows) / n
    burn = sum(b for _, b in rows) / n
    return {"days": n, "intake": round(intake), "intake_range": [round(low), round(high)], "burn": round(burn),
            "burn_range": [round(burn * (1 - WATCH_ERROR)), round(burn * (1 + WATCH_ERROR))],
            "balance_range": [round(low - burn * (1 + WATCH_ERROR)), round(high - burn * (1 - WATCH_ERROR))],
            "balance": round(intake - burn)}


def protein_average(trail: list[dict], weight_kg: float | None) -> dict | None:
    """Mean protein over logged days that have protein figures; None under 4 days. Quick entries without protein are skipped."""
    days = [t for t in trail if t["logged"] and t["protein_g"] is not None]
    if len(days) < MIN_LOGGED_FOR_BALANCE:
        return None
    avg = sum(t["protein_g"] for t in days) / len(days)
    return {"days": len(days), "g": round(avg), "g_per_kg": round(avg / weight_kg, 2) if weight_kg else None}


def implied_expenditure(trail14: list[dict], rate_kg_per_week: float | None, rate_se_kg_per_week: float | None) -> dict | None:
    """What your body seems to burn: mean logged intake minus the energy in the weight-trend change (7,700 kcal/kg, rough).

    Needs 10 logged days in the last 14 and a trend slope. The range carries the intake spread and the slope's own
    uncertainty (1.96 standard errors). Under-logging pulls the answer down, so it reads as 'at least roughly'.
    """
    logged = [t for t in trail14 if t["logged"]]
    if len(logged) < MIN_LOGGED_FOR_IMPLIED or rate_kg_per_week is None:
        return None
    n = len(logged)
    intake = sum(t["kcal"] for t in logged) / n
    low_i = sum(t["kcal_low"] for t in logged) / n
    high_i = sum(t["kcal_high"] for t in logged) / n
    per_kg_day = KCAL_PER_KG / 7
    se = rate_se_kg_per_week or 0.0
    slope_lo, slope_hi = rate_kg_per_week - 1.96 * se, rate_kg_per_week + 1.96 * se
    point = intake - rate_kg_per_week * per_kg_day
    return {"days": n, "kcal": round(point), "range": [round(low_i - slope_hi * per_kg_day), round(high_i - slope_lo * per_kg_day)],
            "intake": round(intake), "trend_kg_week": rate_kg_per_week}


def food_plan(*, weight_kg: float | None, goal_kg: float | None, today_summary: dict, trail: list[dict], trail14: list[dict],
              entries: list[dict], burn_by_day: dict[date, float], today: date, formula: dict | None,
              rate_kg_per_week: float | None, rate_se_kg_per_week: float | None) -> dict:
    """Everything the Food page needs about targets and balance. `formula` is {'bmr': .., 'active': ..} from analytics/body.py."""
    needs = []
    if weight_kg is None:
        needs.append("weight")
    if formula is None:
        needs.append("profile")
    out: dict = {"needs": needs, "phase": phase(weight_kg, goal_kg), "goal_kg": goal_kg, "weight_kg": weight_kg,
                 "reference_energy": None, "targets": None, "today": None, "balance": None, "implied": None, "protein": None,
                 "trend_kg_week": rate_kg_per_week, "meal_protein": meal_protein(entries),
                 "logged_days": sum(1 for t in trail if t["logged"]),
                 "burn_days": sum(1 for t in trail if t["logged"] and burn_by_day.get(t["day"]))}
    if weight_kg is None:
        return out
    ref = reference_energy(burn_by_day, today, formula["active"] if formula else None)
    out["reference_energy"] = ref
    out["targets"] = targets(out["phase"], weight_kg, ref, formula["bmr"] if formula else None)
    out["today"] = day_status(today_summary, out["targets"]["kcal"])
    out["balance"] = balance(trail, burn_by_day)
    out["implied"] = implied_expenditure(trail14, rate_kg_per_week, rate_se_kg_per_week)
    out["protein"] = protein_average(trail, weight_kg)
    return out
