from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, timedelta

KEY_VAR = "GARMIN_API_KEY"
EXPIRY_VAR = "GARMIN_API_KEY_EXPIRES_ON"
REMINDER_VAR = "GARMIN_API_KEY_REMINDER_DAYS"
DEFAULT_THRESHOLDS = (30, 7, 1)


@dataclass(frozen=True)
class CredentialStatus:
    configured: bool
    expires_on: date | None
    days_remaining: int | None
    # missing | invalid_expiry | ok | notice | warning | critical | expired
    level: str
    active_threshold: int | None
    thresholds: tuple[int, ...]
    reminder_dates: tuple[date, ...]

    @property
    def reminder_key(self) -> str | None:
        """Identifies one reminder so dismissal never hides a later escalation."""
        if self.expires_on is None or self.level in ("ok", "missing", "invalid_expiry"):
            return None
        stage = "expired" if self.level == "expired" else str(self.active_threshold)
        return f"{self.expires_on.isoformat()}:{stage}"


def parse_thresholds(raw: str | None) -> tuple[int, ...]:
    if not raw:
        return DEFAULT_THRESHOLDS
    try:
        values = {int(part) for part in raw.split(",") if part.strip()}
    except ValueError:
        return DEFAULT_THRESHOLDS
    values = {v for v in values if v > 0}
    return tuple(sorted(values, reverse=True)) or DEFAULT_THRESHOLDS


def credential_status(values: Mapping[str, str], today: date) -> CredentialStatus:
    configured = bool(values.get(KEY_VAR, "").strip())
    thresholds = parse_thresholds(values.get(REMINDER_VAR))

    if not configured:
        return CredentialStatus(False, None, None, "missing", None, thresholds, ())

    try:
        expires_on = date.fromisoformat(values.get(EXPIRY_VAR, "").strip())
    except ValueError:
        return CredentialStatus(True, None, None, "invalid_expiry", None, thresholds, ())

    days = (expires_on - today).days
    reminder_dates = tuple(expires_on - timedelta(days=t) for t in thresholds)

    if days <= 0:
        return CredentialStatus(
            True, expires_on, days, "expired", None, thresholds, reminder_dates
        )

    crossed = [t for t in thresholds if days <= t]
    if not crossed:
        return CredentialStatus(True, expires_on, days, "ok", None, thresholds, reminder_dates)

    active = min(crossed)
    if active == thresholds[-1]:
        level = "critical"
    elif active == thresholds[0]:
        level = "notice"
    else:
        level = "warning"
    return CredentialStatus(True, expires_on, days, level, active, thresholds, reminder_dates)
