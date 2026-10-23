"""Garmin reports dozens of activity typeKeys; group them for filtering, display, and analytics."""

ACTIVITY_FAMILIES: dict[str, tuple[str, ...]] = {
    "run": ("run",),
    "ride": ("ride", "cycl", "bik"),
    "swim": ("swim",),
    "strength": ("strength", "weight", "hiit", "cardio"),
    "walk": ("walk", "hik"),
    "mind": ("yoga", "pilates", "breath", "stretch", "mobility"),
}


def activity_family(type_key: str) -> str:
    key = type_key.lower()
    return next((f for f, parts in ACTIVITY_FAMILIES.items() if any(p in key for p in parts)), "other")
