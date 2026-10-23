"""Web Push for the website and the iPhone home-screen app, and the scheduler that decides what to send.

Delivery follows RFC 8291 (aes128gcm payload encryption) and RFC 8292 (VAPID). Each notification is logged
under a stable key, so a morning brief, session verdict or reminder is sent at most once.
"""

from __future__ import annotations

import base64
import json
import logging
import os
import threading
import time
from collections.abc import Callable
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import urlsplit

import http_ece
import httpx
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
from py_vapid import Vapid02
from sqlalchemy import delete, select
from sqlalchemy.orm import sessionmaker

from cadence_app import journal, planner_store
from cadence_app.analytics import review as reviews
from cadence_app.analytics import insights, notes
from cadence_app.credentials import CredentialStatus
from cadence_app.models import AppSetting, NotificationLog, PushSubscription, SyncRun

log = logging.getLogger(__name__)
PREFS_KEY = "push_prefs"
PREFS = {
    "morning": "Morning readiness brief",
    "session": "Verdict after each session",
    "bedtime": "Bedtime nudge at 22:30",
    "reminders": "Garmin key renewal reminders",
    "review": "Weekly review (Sunday 19:00) and monthly review (1st, 09:00)",
}
# Only real push services; the endpoint comes from the browser, so this also prevents request forgery.
PUSH_HOSTS = ("push.apple.com", "fcm.googleapis.com", "push.services.mozilla.com", "notify.windows.com")
MAX_FAILURES = 5


def b64url_decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def allowed_endpoint(endpoint: str) -> bool:
    parts = urlsplit(endpoint)
    host = parts.hostname or ""
    return parts.scheme == "https" and any(host == h or host.endswith("." + h) for h in PUSH_HOSTS)


class PushSender:
    def __init__(self, factory: sessionmaker, key_path: Path, contact: str, now: Callable[[], datetime],
                 post: Callable[..., httpx.Response] | None = None):
        self.factory, self.contact, self.now = factory, contact, now
        self.post = post or httpx.post
        self.vapid = self._load_key(key_path)

    @staticmethod
    def _load_key(path: Path) -> Vapid02:
        if path.is_file():
            return Vapid02.from_file(str(path))
        vapid = Vapid02()
        vapid.generate_keys()
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "wb") as fh:
            fh.write(vapid.private_pem())
        return vapid

    @property
    def public_key(self) -> str:
        return b64url(self.vapid.public_key.public_bytes(Encoding.X962, PublicFormat.UncompressedPoint))

    def _deliver(self, sub: PushSubscription, payload: bytes) -> int:
        body = http_ece.encrypt(
            payload, private_key=ec.generate_private_key(ec.SECP256R1()), dh=b64url_decode(sub.p256dh),
            auth_secret=b64url_decode(sub.auth), version="aes128gcm",
        )
        parts = urlsplit(sub.endpoint)
        headers = self.vapid.sign({"aud": f"{parts.scheme}://{parts.netloc}", "exp": int(time.time()) + 12 * 3600, "sub": self.contact})
        headers.update({"TTL": "43200", "Content-Encoding": "aes128gcm", "Content-Type": "application/octet-stream", "Urgency": "normal"})
        return self.post(sub.endpoint, content=body, headers=headers, timeout=10).status_code

    def broadcast(self, title: str, body: str, url: str = "/", tag: str | None = None) -> int:
        payload = json.dumps({"title": title, "body": body, "url": url, "tag": tag}).encode()
        delivered = 0
        with self.factory() as session, session.begin():
            for sub in session.scalars(select(PushSubscription)):
                try:
                    status = self._deliver(sub, payload)
                except (httpx.HTTPError, ValueError) as exc:
                    log.warning("Push delivery failed: %s", type(exc).__name__)
                    status = 0
                if status in (404, 410):
                    session.delete(sub)  # the browser revoked this subscription
                elif 200 <= status < 300:
                    sub.last_sent_at, sub.failures = self.now(), 0
                    delivered += 1
                else:
                    sub.failures += 1
                    if sub.failures >= MAX_FAILURES:
                        session.delete(sub)
        return delivered


def get_prefs(factory: sessionmaker) -> dict[str, bool]:
    with factory() as session:
        row = session.get(AppSetting, PREFS_KEY)
    saved = json.loads(row.value) if row else {}
    return {k: bool(saved.get(k, True)) for k in PREFS}


def set_prefs(factory: sessionmaker, prefs: dict[str, bool]) -> dict[str, bool]:
    clean = {k: bool(prefs.get(k, True)) for k in PREFS}
    with factory() as session, session.begin():
        row = session.get(AppSetting, PREFS_KEY)
        if row:
            row.value = json.dumps(clean)
        else:
            session.add(AppSetting(key=PREFS_KEY, value=json.dumps(clean)))
    return clean


def _clock(minutes: float) -> str:
    m = round(minutes) % 1440
    return f"{m // 60:02d}:{m % 60:02d}"


def bedtime_due(now_local: datetime, tonight: dict | None) -> bool:
    """45 minutes before tonight's bedtime (never before 19:00; a bedtime after midnight is nudged at 23:30)."""
    if not tonight:
        return False
    trigger = tonight["bed_min"] - 45  # minutes from tomorrow's midnight; negative = this evening
    trigger = 1440 + trigger if trigger < 0 else 23 * 60 + 30
    trigger = max(trigger, 19 * 60)
    return now_local.hour * 60 + now_local.minute >= trigger


def _first_sentence(text: str, limit: int = 160) -> str:
    cut = text.split(". ")[0].rstrip(".") + "."
    return cut if len(cut) <= limit else cut[: limit - 1].rstrip() + "…"


class Notifier:
    """Decides which notifications are due; `tick` is idempotent and safe to call every few minutes."""

    def __init__(self, factory: sessionmaker, sender: PushSender, source: Callable[[], str],
                 credential: Callable[[], CredentialStatus]):
        self.factory, self.sender, self.source, self.credential = factory, sender, source, credential

    def _logged(self, key: str) -> bool:
        with self.factory() as session:
            return session.get(NotificationLog, key) is not None

    def _send(self, key: str, kind: str, title: str, body: str, url: str, now: datetime) -> bool:
        delivered = self.sender.broadcast(title, body, url, tag=kind)
        with self.factory() as session, session.begin():
            session.merge(NotificationLog(key=key, kind=kind, title=title, body=body, sent_at=now, delivered=delivered))
        return delivered > 0

    def due(self, now_local: datetime) -> list[dict]:
        """Notifications that should go out now and haven't been sent yet."""
        prefs = get_prefs(self.factory)
        today = now_local.date()
        out: list[dict] = []
        with self.factory() as session:
            c = insights.context(session, self.source(), today)

        if prefs["reminders"]:
            cred = self.credential()
            if cred.reminder_key:
                days = cred.days_remaining or 0
                title = "Garmin key expired" if days <= 0 else f"Garmin key expires in {days} day{'s' if days != 1 else ''}"
                out.append({"key": f"key:{cred.reminder_key}", "kind": "reminders", "title": title, "url": "/settings",
                            "body": "Renew it in the Garmin developer portal, then update the local secrets file."})
        if c is None:
            return [n for n in out if not self._logged(n["key"])]

        if prefs["morning"] and 6 <= now_local.hour < 12:
            r = insights.readiness_on(c, today)
            if r is not None and c["as_of"] == today:
                b = notes.brief(c)
                with self.factory() as session:
                    pending = not journal.checkin(session, today)["done"]
                out.append({"key": f"morning:{today}", "kind": "morning", "url": "/?checkin=1" if pending else "/",
                            "title": f"Readiness {r['score']} · {b['call']['headline']}" if b["call"] else f"Readiness {r['score']}",
                            "body": f"{b['today']['title']}. {_first_sentence(b['today']['detail'])}"
                                    + (" Tap to log yesterday's habits." if pending else "")})

        if prefs["session"]:
            cutoff = now_local - timedelta(hours=36)
            hard = notes.hard_days(c)
            for a in c["acts"]:
                if a.start_local is None or a.start_local < cutoff:
                    continue
                v = notes.verdict(a, hard)
                s = notes.session(c, a.id)
                top = next((n for n in s["notes"] if n["severity"] in ("alert", "warn")), s["notes"][0] if s["notes"] else None) if s else None
                if v is None and top is None:
                    continue
                out.append({"key": f"session:{a.id}", "kind": "session", "url": f"/activities/{a.id}",
                            "title": f"{v['label']} · {a.name}" if v else a.name,
                            "body": f"{top['title']}. {_first_sentence(top['detail'])}" if top else "Session analysed."})

        tonight = c.get("tonight") if c["as_of"] == today else None
        if prefs["bedtime"] and bedtime_due(now_local, tonight):
            parts = [f"{tonight['tonight_h']:.1f} h tonight to wake at {_clock(tonight['wake_min'])}"]
            if tonight["extra_load_min"]:
                parts.append(f"+{tonight['extra_load_min']} min for today's training")
            if tonight["repay_min"]:
                parts.append(f"+{tonight['repay_min']} min toward this week's {tonight['debt_h']:.1f} h debt")
            out.append({"key": f"bedtime:{today}", "kind": "bedtime", "url": "/metrics/sleep_hours",
                        "title": f"In bed by {_clock(tonight['bed_min'])}", "body": "; ".join(parts) + ". Start winding down now."})
        elif prefs["bedtime"] and tonight is None and (now_local.hour, now_local.minute) >= (22, 30):
            need = notes.need(c)
            out.append({"key": f"bedtime:{today}", "kind": "bedtime", "url": "/metrics/sleep_hours",
                        "title": "Lights out by 23:30", "body": f"Wind down now: {need:g} h tonight lets today's training land."})

        if prefs["review"]:
            out += self._reviews(c, now_local)
        return [n for n in out if not self._logged(n["key"])]

    def _reviews(self, c: dict, now_local: datetime) -> list[dict]:
        today = now_local.date()
        due = []
        if today.weekday() == 6 and now_local.hour >= 19:
            due.append(("week", today - timedelta(days=6), f"review-week:{today - timedelta(days=6)}", "Week in review"))
        if today.day == 1 and now_local.hour >= 9:
            first = (today - timedelta(days=1)).replace(day=1)
            due.append(("month", first, f"review-month:{first:%Y-%m}", f"{first:%B} in review"))
        out = []
        for kind, start, key, label in due:
            if self._logged(key):
                continue
            with self.factory() as session:
                planned = planner_store.reconcile(session, self.source(), planner_store.listing(session, start - timedelta(days=62), today),
                                                  today, datetime.now())
            r = reviews.build(c, kind, start, planned, insights.readiness_on)
            out.append({"key": key, "kind": "review", "url": f"/review?kind={kind}&start={start}",
                        "title": f"{label}: {r['verdict']}", "body": reviews.headline(r)})
        return out

    def tick(self, now_local: datetime, now_utc: datetime) -> list[str]:
        with self.factory() as session:
            if session.scalar(select(PushSubscription.id).limit(1)) is None:
                return []
        sent = []
        for n in self.due(now_local):
            self._send(n["key"], n["kind"], n["title"], n["body"], n["url"], now_utc)
            sent.append(n["key"])
        return sent

    def recent(self, limit: int = 8) -> list[dict]:
        with self.factory() as session:
            rows = session.scalars(select(NotificationLog).order_by(NotificationLog.sent_at.desc()).limit(limit)).all()
            return [{"kind": r.kind, "title": r.title, "body": r.body, "sent_at": r.sent_at, "delivered": r.delivered} for r in rows]


def subscribe(factory: sessionmaker, endpoint: str, p256dh: str, auth: str, label: str, now: datetime) -> None:
    with factory() as session, session.begin():
        sub = session.scalar(select(PushSubscription).where(PushSubscription.endpoint == endpoint))
        if sub is None:
            session.add(PushSubscription(endpoint=endpoint, p256dh=p256dh, auth=auth, label=label, created_at=now, failures=0))
        else:
            sub.p256dh, sub.auth, sub.label, sub.failures = p256dh, auth, label, 0


def unsubscribe(factory: sessionmaker, endpoint: str) -> None:
    with factory() as session, session.begin():
        session.execute(delete(PushSubscription).where(PushSubscription.endpoint == endpoint))


def devices(factory: sessionmaker) -> list[dict]:
    with factory() as session:
        return [{"label": s.label, "created_at": s.created_at, "last_sent_at": s.last_sent_at, "endpoint_host": urlsplit(s.endpoint).hostname}
                for s in session.scalars(select(PushSubscription).order_by(PushSubscription.created_at))]


class Scheduler:
    """Background loop: keeps Garmin data fresh and sends due notifications."""

    def __init__(self, factory: sessionmaker, notifier: Notifier, sync: Callable[[str], object], sync_busy: Callable[[], bool],
                 can_sync: Callable[[], bool], now_utc: Callable[[], datetime], sync_every_h: float, interval_s: float = 300):
        self.factory, self.notifier, self.sync, self.sync_busy, self.can_sync = factory, notifier, sync, sync_busy, can_sync
        self.now_utc, self.sync_every_h, self.interval_s = now_utc, sync_every_h, interval_s
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread is None:
            self._thread = threading.Thread(target=self._loop, daemon=True, name="cadence-scheduler")
            self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def _loop(self) -> None:
        self._stop.wait(20)  # let startup settle
        while not self._stop.is_set():
            try:
                self.run_once(datetime.now(), self.now_utc())
            except Exception:  # pylint: disable=broad-exception-caught  # background job boundary
                log.exception("Scheduler tick failed")
            self._stop.wait(self.interval_s)

    def last_sync(self) -> datetime | None:
        with self.factory() as session:
            return session.scalar(
                select(SyncRun.started_at).where(SyncRun.source_id == "garmin", SyncRun.mode.in_(("quick", "full")))
                .order_by(SyncRun.id.desc()).limit(1)
            )

    def sync_due(self, now_local: datetime, now_utc: datetime) -> bool:
        if self.sync_every_h <= 0 or self.sync_busy() or not self.can_sync():
            return False
        last = self.last_sync()
        every = timedelta(hours=self.sync_every_h)
        # Mornings refresh fastest for the readiness brief; waking hours hourly so live readiness tracks the day.
        if 6 <= now_local.hour < 11:
            every = min(every, timedelta(minutes=45))
        elif 11 <= now_local.hour < 23:
            every = min(every, timedelta(hours=1))
        return last is None or now_utc - last >= every

    def run_once(self, now_local: datetime, now_utc: datetime) -> list[str]:
        if self.sync_due(now_local, now_utc):
            try:
                self.sync("quick")
            except RuntimeError:
                pass  # another job started in between
        return self.notifier.tick(now_local, now_utc)
