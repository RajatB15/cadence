"""Body-composition estimates from weight + a stored profile (height, birth date, sex).

Everything here is a formula applied to your logged weight and profile - never a body-composition
measurement. Nothing in Cadence measures fat, muscle or water directly, so every figure below is shown as an
estimate with its source and typical error. (Garmin Index scales do measure impedance; if that ever lands in
the vault it would be shown as a measured value separately, not folded into these.)

- BMI: weight_kg / height_m², exact arithmetic, not an estimate. Category cutoffs are WHO's general-adult
  thresholds and are known to misclassify very muscular people.
- Body fat %: Deurenberg, Weststrate & Seidell (1991), "Body mass index as a measure of body fatness:
  age- and sex-specific prediction formulas", Br J Nutr 65(2):105-14. BF% = 1.2*BMI + 0.23*age - 10.8*sex -
  5.4 (sex: 1 male, 0 female). Derived from a general adult population against underwater-weighing reference;
  the paper's own standard error of estimate is about 4 percentage points, and it tends to overestimate body
  fat in very lean or muscular people. Fat/lean mass are this percentage applied to weight, so they carry the
  same uncertainty.
- BMR: Mifflin, St Jeor et al. (1990), "A new predictive equation for resting energy expenditure in healthy
  individuals", Am J Clin Nutr 51(2):241-7. One of the better-validated resting-energy equations for the
  general population; still only accurate to roughly ±10% for a given individual.
- Healthy range: the weights at BMI 18.5 and 24.9 for your height (WHO adult cut-offs) - exact arithmetic.
- Body surface area: Mosteller (1987), N Engl J Med 317:1098, sqrt(height_cm * weight_kg / 3600).
- Daily energy: BMR x physical-activity level, using the lower bound of the FAO/WHO/UNU (2004) PAL bands -
  light 1.4, active 1.7, vigorous 2.0. A planning range, not a prescription; real needs vary by about +-10%
  on top of the BMR error.

Muscle %, bone mass, visceral fat, water % and metabolic age are deliberately not computed: there is no
credible formula for them from weight/height/age/sex alone (they need an actual impedance measurement), and
inventing one would violate this project's own measured-vs-calculated rule.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from math import sqrt

from cadence_app.profile import age_years

HEALTHY_BMI = (18.5, 24.9)
PAL = {"light": 1.4, "active": 1.7, "vigorous": 2.0}
BMI_CATEGORIES = ((18.5, "underweight"), (25.0, "normal"), (30.0, "overweight"), (float("inf"), "obese"))


@dataclass(frozen=True)
class BodyEstimate:
    bmi: float
    bmi_category: str
    body_fat_pct: float
    fat_mass_kg: float
    lean_mass_kg: float
    bmr_kcal: float
    healthy_min_kg: float
    healthy_max_kg: float
    to_healthy_kg: float  # 0 inside the range; negative = above it (kg to lose), positive = below it
    bsa_m2: float
    energy_kcal: dict[str, int]


def bmi_category(bmi: float) -> str:
    return next(label for ceiling, label in BMI_CATEGORIES if bmi < ceiling)


def estimate(weight_kg: float, profile: dict, as_of: date) -> BodyEstimate | None:
    """None if weight or the profile's height is out of a sane range for these formulas to mean anything."""
    height_m = profile["height_cm"] / 100
    if not (20 < weight_kg < 300) or not (1.0 < height_m < 2.5):
        return None
    age = age_years(profile["birth_date"], as_of)
    sex_term = 1 if profile["sex"] == "male" else 0
    bmi = weight_kg / height_m**2
    bf_pct = max(2.0, min(70.0, 1.2 * bmi + 0.23 * age - 10.8 * sex_term - 5.4))
    fat_mass = weight_kg * bf_pct / 100
    bmr = 10 * weight_kg + 6.25 * profile["height_cm"] - 5 * age + (5 if sex_term else -161)
    low, high = HEALTHY_BMI[0] * height_m**2, HEALTHY_BMI[1] * height_m**2
    to_healthy = 0.0 if low <= weight_kg <= high else (low - weight_kg if weight_kg < low else high - weight_kg)
    return BodyEstimate(
        bmi=round(bmi, 1), bmi_category=bmi_category(bmi), body_fat_pct=round(bf_pct, 1),
        fat_mass_kg=round(fat_mass, 1), lean_mass_kg=round(weight_kg - fat_mass, 1), bmr_kcal=round(bmr),
        healthy_min_kg=round(low, 1), healthy_max_kg=round(high, 1), to_healthy_kg=round(to_healthy, 1),
        bsa_m2=round(sqrt(profile["height_cm"] * weight_kg / 3600), 2),
        energy_kcal={name: round(bmr * level) for name, level in PAL.items()},
    )
