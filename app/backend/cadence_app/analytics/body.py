"""Body-composition estimates from weight + a stored profile (height, birth date, sex).

Everything here is a formula applied to weight — never a scale measurement. This scale (SSW526, see
docs/protocol-investigation.md) has not been shown to transmit body composition at all; its official app's
own UI attributes those numbers to "your initial info" (the stored profile), consistent with the same kind
of formula-based estimate used here, not a bioimpedance reading. If a future capture confirms the scale
sends real impedance data, that would become a *measured* value elsewhere, replacing the relevant estimate
here — until then, nothing below is presented as more than an estimate.

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

Muscle %, bone mass, visceral fat, water % and metabolic age are deliberately not computed: there is no
credible formula for them from weight/height/age/sex alone (they need an actual impedance measurement), and
inventing one would violate this project's own measured-vs-calculated rule.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from cadence_app.profile import age_years

BMI_CATEGORIES = ((18.5, "underweight"), (25.0, "normal"), (30.0, "overweight"), (float("inf"), "obese"))


@dataclass(frozen=True)
class BodyEstimate:
    bmi: float
    bmi_category: str
    body_fat_pct: float
    fat_mass_kg: float
    lean_mass_kg: float
    bmr_kcal: float


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
    return BodyEstimate(
        bmi=round(bmi, 1), bmi_category=bmi_category(bmi), body_fat_pct=round(bf_pct, 1),
        fat_mass_kg=round(fat_mass, 1), lean_mass_kg=round(weight_kg - fat_mass, 1), bmr_kcal=round(bmr),
    )
