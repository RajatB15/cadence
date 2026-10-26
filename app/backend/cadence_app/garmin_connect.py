"""Optional, unofficial link to Garmin Connect, used only to send planned workouts to your watch.

This is not the Personal API key used for syncing (that one is read-only). It signs in to Garmin Connect the way
the website does, through the open-source `garminconnect` library, so it can break when Garmin changes its login
and may be against Garmin's terms of use. It is off until you connect, creates and schedules workouts only, and
never reads or writes activities or health data.

Your password is used for the sign-in request and then dropped: it is never stored, logged or returned. Only the
session tokens are kept, in a 0700 directory beside the secrets file (the library writes them 0600). Sign-in is
attempted once per connect; afterwards the saved tokens are reused, because repeated sign-ins are what Garmin's
login protection blocks. Rate limits and auth failures stop and are reported, never retried in a loop.
"""

from __future__ import annotations

import shutil
import threading
import time
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from cadence_app import garmin_workout

MFA_WAIT_S = 600


class ConnectError(Exception):
    """A message safe to show: it never contains credentials."""


class NotConnected(ConnectError):
    pass


def _library() -> Any:
    try:
        import garminconnect
    except ImportError as e:
        raise ConnectError("Install the optional dependency first: pip install 'garminconnect>=0.3.20'") from e
    return garminconnect


def available() -> bool:
    try:
        _library()
    except ConnectError:
        return False
    return True


@dataclass
class _Pending:
    client: Any
    state: Any
    at: float


class GarminConnectLink:
    def __init__(self, token_dir: Path):
        self.token_dir = token_dir
        self._pending: _Pending | None = None
        self._lock = threading.Lock()

    # -- status ------------------------------------------------------------------------------

    def status(self) -> dict:
        return {"available": available(), "connected": self.token_dir.is_dir() and any(self.token_dir.iterdir()),
                "awaiting_code": self._pending is not None and time.monotonic() - self._pending.at < MFA_WAIT_S}

    # -- sign-in -----------------------------------------------------------------------------

    def connect(self, email: str, password: str) -> dict:
        """Sign in once. Returns {"status": "connected"} or {"status": "needs_code"} when Garmin asks for MFA."""
        gc = _library()
        with self._lock:
            client = gc.Garmin(email.strip(), password, return_on_mfa=True)
            try:
                status, state = client.login()
            except gc.GarminConnectTooManyRequestsError as e:
                raise ConnectError("Garmin is limiting sign-ins. Wait at least 15 minutes before trying again.") from e
            except gc.GarminConnectAuthenticationError as e:
                raise ConnectError("Garmin rejected that email or password.") from e
            except Exception as e:  # the library's messages can quote server responses; keep ours generic
                raise ConnectError(f"Couldn't reach Garmin Connect ({type(e).__name__}).") from e
            finally:
                password = ""
                client.password = None
            if status == "needs_mfa":
                self._pending = _Pending(client, state, time.monotonic())
                return {"status": "needs_code"}
            self._save(client)
            return {"status": "connected"}

    def submit_code(self, code: str) -> dict:
        gc = _library()
        with self._lock:
            pending, self._pending = self._pending, None
            if pending is None or time.monotonic() - pending.at > MFA_WAIT_S:
                raise ConnectError("That sign-in expired. Start again.")
            try:
                pending.client.resume_login(pending.state, code.strip())
            except gc.GarminConnectAuthenticationError as e:
                raise ConnectError("Garmin rejected that code. Start again.") from e
            except Exception as e:
                raise ConnectError(f"Couldn't finish the sign-in ({type(e).__name__}).") from e
            self._save(pending.client)
            return {"status": "connected"}

    def disconnect(self) -> None:
        self._pending = None
        shutil.rmtree(self.token_dir, ignore_errors=True)

    def _save(self, client: Any) -> None:
        self.token_dir.mkdir(parents=True, exist_ok=True)
        self.token_dir.chmod(0o700)
        client.client.dump(str(self.token_dir))

    def _client(self) -> Any:
        if not self.status()["connected"]:  # before the import: a missing optional library must not mask "not connected"
            raise NotConnected("Connect Garmin first (Settings).")
        gc = _library()
        client = gc.Garmin()
        try:
            client.login(tokenstore=str(self.token_dir))  # saved tokens only: no password, no new sign-in
        except gc.GarminConnectTooManyRequestsError as e:
            raise ConnectError("Garmin is limiting requests. Try again in a few minutes.") from e
        except Exception as e:
            raise NotConnected("Garmin signed you out. Connect again in Settings.") from e
        return client

    # -- workouts ----------------------------------------------------------------------------

    def send(self, plan: dict, day: date) -> dict:
        """Create the workout and put it on your Garmin calendar for `day`; the watch picks it up on its next sync."""
        workout = garmin_workout.build(plan)
        client = self._client()
        try:
            created = client.upload_workout(workout)
            workout_id = int(created["workoutId"])
            scheduled = client.schedule_workout(workout_id, day.isoformat())
        except KeyError as e:
            raise ConnectError("Garmin accepted the request but didn't return a workout id.") from e
        except Exception as e:
            raise ConnectError(f"Garmin refused the workout ({type(e).__name__}).") from e
        schedule_id = scheduled.get("workoutScheduleId") if isinstance(scheduled, dict) else None
        return {"workout_id": workout_id, "schedule_id": int(schedule_id) if schedule_id else None}

    def remove(self, workout_id: int, schedule_id: int | None) -> None:
        """Take a workout Cadence sent off the calendar and out of the library. Already-gone is fine."""
        client = self._client()
        for call, ident in ((client.unschedule_workout, schedule_id), (client.delete_workout, workout_id)):
            if ident is None:
                continue
            try:
                call(ident)
            except Exception as e:
                if "404" not in str(e) and "not found" not in str(e).lower():
                    raise ConnectError(f"Garmin wouldn't remove the workout ({type(e).__name__}).") from e
