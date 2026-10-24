"""Last-backup status for the Settings page.

`deploy/backup.sh` (the nightly Google Drive backup on the server) writes `backup-status.json` into the data
directory after every run; this only reads it. A machine that never ran a backup has no file, which is reported as
"not configured", not as a failure. Times are naive UTC, like everywhere else in the API.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path

STATUS_FILE = "backup-status.json"
STALE_AFTER = timedelta(hours=36)  # nightly job; one missed night is a warning, not noise


def _parse(value) -> datetime | None:
    try:
        return datetime.fromisoformat(value) if isinstance(value, str) else None
    except ValueError:
        return None


def load(data_dir: Path, now: datetime) -> dict:
    try:
        raw = json.loads((data_dir / STATUS_FILE).read_text())
        if not isinstance(raw, dict):
            raise ValueError
    except (OSError, ValueError):
        return {"configured": False}
    success, attempt = _parse(raw.get("last_success_at")), _parse(raw.get("last_attempt_at"))
    error = raw.get("last_error")
    return {
        "configured": True,
        "last_success_at": success,
        "last_attempt_at": attempt,
        "snapshot": raw.get("snapshot") if isinstance(raw.get("snapshot"), str) else None,
        "last_error": error if isinstance(error, str) and error else None,
        "stale": success is None or now - success > STALE_AFTER,
    }
