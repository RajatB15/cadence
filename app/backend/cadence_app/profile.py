"""Body profile: height, birth date and biological sex — used only by the body-composition formulas in
`analytics/body.py`, nothing else. Stored as one JSON `AppSetting`, like the training/weight goals.
"""

from __future__ import annotations

import json
from datetime import date

from sqlalchemy.orm import Session

from cadence_app.models import AppSetting

PROFILE_KEY = "body_profile"
MIN_HEIGHT_CM, MAX_HEIGHT_CM = 100.0, 250.0


def load(session: Session) -> dict | None:
    row = session.get(AppSetting, PROFILE_KEY)
    if not row:
        return None
    try:
        data = json.loads(row.value)
        return {"height_cm": float(data["height_cm"]), "birth_date": date.fromisoformat(data["birth_date"]), "sex": data["sex"]}
    except (ValueError, KeyError, TypeError):
        return None


def save(session: Session, height_cm: float, birth_date: date, sex: str) -> dict:
    if sex not in ("male", "female"):
        raise ValueError("sex must be 'male' or 'female' (used only by the body-composition formulas)")
    if not MIN_HEIGHT_CM <= height_cm <= MAX_HEIGHT_CM:
        raise ValueError(f"height must be between {MIN_HEIGHT_CM:g} and {MAX_HEIGHT_CM:g} cm")
    if birth_date >= date.today() or birth_date.year < 1900:
        raise ValueError("birth date looks wrong")
    value = json.dumps({"height_cm": height_cm, "birth_date": birth_date.isoformat(), "sex": sex})
    row = session.get(AppSetting, PROFILE_KEY)
    if row:
        row.value = value
    else:
        session.add(AppSetting(key=PROFILE_KEY, value=value))
    session.commit()
    return {"height_cm": height_cm, "birth_date": birth_date, "sex": sex}


def age_years(birth_date: date, as_of: date) -> float:
    days = (as_of - birth_date).days
    return max(0.0, days / 365.2425)
