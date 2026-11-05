"""The user's timezone for the 'today' clock.

Stored as one `AppSetting` holding an IANA name. Without it, the machine's local zone is used. The
server may run somewhere other than where the user is (a VPS in UTC), so an explicit zone keeps
"today" and the day rollover correct. Instants stay naive UTC in the database; only the local
calendar day is derived from the zone.
"""

from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy.orm import Session

from cadence_app.models import AppSetting

KEY = "timezone"


def validate(name: str) -> str:
    name = (name or "").strip()
    if not name or len(name) > 64 or name.startswith("/") or ".." in name:
        raise ValueError("Unknown timezone")
    try:
        ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError, OSError):
        raise ValueError("Unknown timezone (use an IANA name such as Europe/London)") from None
    return name


def load(session: Session) -> str | None:
    row = session.get(AppSetting, KEY)
    if row is None:
        return None
    try:
        return validate(row.value)
    except ValueError:
        return None


def save(session: Session, name: str | None) -> str | None:
    row = session.get(AppSetting, KEY)
    if name in (None, ""):
        if row is not None:
            session.delete(row)
        session.commit()
        return None
    name = validate(name)
    if row is None:
        session.add(AppSetting(key=KEY, value=name))
    else:
        row.value = name
    session.commit()
    return name


def zone(name: str | None):
    """tzinfo for a stored name, or the system local zone (aware) when unset."""
    if name:
        return ZoneInfo(name)
    return system_zone()


def system_zone():
    """The machine's zone as a real tzinfo (so past instants get the offset that applied then, DST included); fixed offset only as a last resort."""
    import os

    candidates = [os.environ.get("TZ", "").lstrip(":")]
    try:
        target = os.path.realpath("/etc/localtime")
        if "zoneinfo/" in target:
            candidates.append(target.split("zoneinfo/", 1)[1])
    except OSError:
        pass
    for cand in candidates:
        if cand:
            try:
                return ZoneInfo(cand)
            except (ZoneInfoNotFoundError, ValueError, OSError):
                continue
    return datetime.now().astimezone().tzinfo


def today_in(name: str | None, instant: datetime | None = None) -> date:
    """Local calendar day. `instant` is aware, or naive UTC."""
    tz = zone(name)
    if instant is None:
        return datetime.now(tz).date()
    if instant.tzinfo is None:
        from datetime import UTC

        instant = instant.replace(tzinfo=UTC)
    return instant.astimezone(tz).date()
