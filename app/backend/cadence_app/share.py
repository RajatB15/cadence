"""Read-only phone access over the local network, paired with a QR code shown on the Mac."""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import re
import secrets
import shutil
import socket
import subprocess
import threading
import time
from collections.abc import Callable
from datetime import datetime, timezone
from html import escape
from pathlib import Path

import segno
import uvicorn
from sqlalchemy.orm import sessionmaker
from starlette.requests import Request
from starlette.responses import FileResponse, HTMLResponse, JSONResponse, PlainTextResponse, RedirectResponse, Response
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from cadence_app.models import AppSetting

log = logging.getLogger(__name__)
COOKIE = "cadence_share"
SECURE_COOKIE = "__Host-cadence_share"  # the __Host- prefix is only valid on a Secure cookie
TOKEN_KEY, ENABLED_KEY = "share_token", "share_enabled"  # TOKEN_KEY is the pre-session shared key, kept only to upgrade old phones
SESSIONS_KEY, LEGACY_UNTIL_KEY = "share_sessions", "share_legacy_until"
COOKIE_MAX_AGE = 180 * 86400
PAIRING_TTL_S = 10 * 60
LEGACY_GRACE_S = 30 * 86400
MAX_SESSIONS = 20
FAIL_FREE, FAIL_MAX_BLOCK_S = 5, 15 * 60
SHARED_BUCKET_MAX_BLOCK_S = 60  # tailscale serve / reverse proxies show every peer as loopback: one peer must not lock out the rest for long
LOOPBACK = ("127.0.0.1", "::1", "localhost")
GLOBAL_FAIL_WINDOW_S, GLOBAL_FAIL_MAX = 10 * 60, 60  # bad guesses from anywhere; limits a spread-out guesser, never a valid key
BLOCKED_API = ("/api/share",)
# The only writes a paired phone may make, as anchored (method, regex) pairs matched against the whole path.
# Everything else (Garmin push/delete of planned sessions, reading feed refresh, credentials, goals, rebuilds, sharing) stays on the Mac.
_SEG = r"[^/]+"
PHONE_WRITES: tuple[tuple[str, re.Pattern[str]], ...] = tuple(
    (method, re.compile(pattern))
    for method, pattern in (
        ("POST", r"/api/push/(subscribe|unsubscribe|test)"),
        ("PUT", r"/api/push/prefs"),
        ("POST", r"/api/garmin/sync"),
        ("POST", r"/api/activities/[0-9]+/fetch"),
        ("PUT", rf"/api/journal/{_SEG}"),
        ("POST", r"/api/journal/behaviours"),
        ("PATCH", rf"/api/journal/behaviours/{_SEG}"),
        ("PUT", rf"/api/wellbeing/{_SEG}"),
        ("DELETE", rf"/api/wellbeing/{_SEG}"),
        ("POST", r"/api/strength/(parse|ocr)"),
        ("PUT", rf"/api/strength/{_SEG}"),
        ("DELETE", rf"/api/strength/{_SEG}"),
        ("POST", r"/api/planner"),
        ("DELETE", rf"/api/planner/{_SEG}"),
        ("PUT", rf"/api/reading/{_SEG}"),
        ("POST", r"/api/phases"),
        ("PUT", rf"/api/phases/{_SEG}"),
        ("DELETE", rf"/api/phases/{_SEG}"),
        ("POST", r"/api/weight/entries"),
        ("DELETE", rf"/api/weight/entries/{_SEG}"),
        ("POST", r"/api/food/(dishes|entries|meals|copy|label|label/text)"),
        ("PATCH", rf"/api/food/(dishes|entries|meals)/{_SEG}"),
        ("DELETE", rf"/api/food/(entries|meals)/{_SEG}"),
        ("POST", rf"/api/food/meals/{_SEG}/log"),
        ("PUT", r"/api/settings/(weather|profile|plan)"),
        ("POST", r"/api/time-off"),
        ("PUT", rf"/api/time-off/{_SEG}"),
        ("DELETE", rf"/api/time-off/{_SEG}"),
    )
)


def phone_may_write(method: str, path: str) -> bool:
    return any(m == method and rx.fullmatch(path) for m, rx in PHONE_WRITES)


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _label(user_agent: str) -> str:
    ua = user_agent.lower()
    device = next((n for k, n in (("iphone", "iPhone"), ("ipad", "iPad"), ("android", "Android"), ("macintosh", "Mac"), ("windows", "Windows")) if k in ua), "Device")
    browser = next((n for k, n in (("edg", "Edge"), ("chrome", "Chrome"), ("firefox", "Firefox"), ("safari", "Safari")) if k in ua), "")
    return f"{device} {browser}".strip()


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")


class ShareAuth:
    """Per-device sessions. A phone pairs once with a short-lived single-use key and gets its own random session token;
    only the SHA-256 of each token is stored, so a copy of the vault can't be replayed as a cookie, and one phone can be revoked alone."""

    def __init__(self, load: Callable[[str], str | None], save: Callable[[str, str | None], None], clock: Callable[[], float] = time.time):
        self._load, self._save, self._clock = load, save, clock
        self._lock = threading.Lock()
        self._pairing: tuple[str, float] | None = None  # (key, expires) held in memory only
        self._fails: dict[str, tuple[int, float]] = {}  # client -> (failures, blocked until)
        self._seen: dict[str, float] = {}
        self._global_fails: list[float] = []
        self._upgraded: dict[str, str] = {}  # sha256(legacy cookie) -> the session minted for it, so parallel loads share one

    # --- storage
    def _sessions(self) -> dict[str, dict]:
        try:
            data = json.loads(self._load(SESSIONS_KEY) or "{}")
        except ValueError:
            return {}
        return data if isinstance(data, dict) else {}

    def _store(self, sessions: dict[str, dict]) -> None:
        self._save(SESSIONS_KEY, json.dumps(sessions))

    # --- pairing key
    def pairing_key(self) -> tuple[str, float]:
        """The current QR key, minted afresh when missing or expired. Single use: pairing consumes it."""
        with self._lock:
            now = self._clock()
            if self._pairing is None or self._pairing[1] <= now:
                self._pairing = (secrets.token_urlsafe(32), now + PAIRING_TTL_S)
            return self._pairing

    def rotate_pairing_key(self) -> None:
        with self._lock:
            self._pairing = None

    # --- failed-pair throttle
    def blocked_for(self, client: str) -> int:
        _, until = self._fails.get(client, (0, 0.0))
        return max(0, int(until - self._clock() + 0.999))

    def global_blocked(self) -> bool:
        now = self._clock()
        self._global_fails = [t for t in self._global_fails if now - t < GLOBAL_FAIL_WINDOW_S]
        return len(self._global_fails) >= GLOBAL_FAIL_MAX

    def _fail(self, client: str) -> None:
        count, _ = self._fails.get(client, (0, 0.0))
        count += 1
        cap = SHARED_BUCKET_MAX_BLOCK_S if client in LOOPBACK else FAIL_MAX_BLOCK_S
        delay = min(cap, 2 ** (count - FAIL_FREE) * 15) if count > FAIL_FREE else 0
        self._global_fails.append(self._clock())
        if len(self._fails) > 1000:
            self._fails.clear()
        self._fails[client] = (count, self._clock() + delay)
        log.warning("Failed phone pairing attempt #%d from %s (blocked for %ds)", count, client, delay)

    # --- sessions
    def pair(self, key: str, client: str, user_agent: str = "") -> str | None:
        """Session token for a valid, unexpired, unused key; None otherwise (counted against the client)."""
        return self.try_pair(key, client, user_agent)[0]

    def try_pair(self, key: str, client: str, user_agent: str = "") -> tuple[str | None, int]:
        """(token, 0) for a valid key, whoever is blocked: the key is 256 bits, so throttling only matters for wrong guesses.
        Otherwise (None, seconds to wait) when the client or the whole server is throttled (not counted again), or (None, 0) for a fresh miss."""
        with self._lock:
            now = self._clock()
            ok = self._pairing is not None and self._pairing[1] > now and hmac.compare_digest(key.encode(), self._pairing[0].encode())
            if ok:
                self._pairing = None  # single use
                self._fails.pop(client, None)
                return self._new_session(user_agent), 0
            if wait := self.blocked_for(client):
                return None, wait
            if self.global_blocked():
                return None, 60
            self._fail(client)
            return None, 0

    def _new_session(self, user_agent: str) -> str:
        token = secrets.token_urlsafe(32)
        sessions = self._sessions()
        sid = secrets.token_hex(6)
        sessions[sid] = {"hash": _hash(token), "label": _label(user_agent), "created_at": _now_iso(), "last_seen_at": _now_iso()}
        while len(sessions) > MAX_SESSIONS:
            sessions.pop(min(sessions, key=lambda k: sessions[k].get("last_seen_at", "")))
        self._store(sessions)
        return token

    def check(self, token: str) -> str | None:
        """Session id for a valid cookie value, else None."""
        if not token:
            return None
        digest = _hash(token)
        for sid, rec in self._sessions().items():
            if hmac.compare_digest(str(rec.get("hash", "")), digest):
                self._touch(sid)
                return sid
        return None

    def _touch(self, sid: str) -> None:
        now = self._clock()
        if now - self._seen.get(sid, 0) < 300:
            return
        self._seen[sid] = now
        with self._lock:
            sessions = self._sessions()
            if sid in sessions:
                sessions[sid]["last_seen_at"] = _now_iso()
                self._store(sessions)

    def legacy_valid(self, cookie: str) -> bool:
        """Phones paired before per-device sessions carry the old shared key; it keeps working for a grace period."""
        legacy = self._load(TOKEN_KEY)
        if not legacy or not cookie or not hmac.compare_digest(cookie.encode(), legacy.encode()):
            return False
        until = self._load(LEGACY_UNTIL_KEY)
        if until is None:
            until = str(int(self._clock() + LEGACY_GRACE_S))
            self._save(LEGACY_UNTIL_KEY, until)
        if self._clock() > float(until):
            self._save(TOKEN_KEY, None)
            return False
        return True

    def upgrade_legacy(self, user_agent: str, legacy_cookie: str = "") -> str:
        """Swaps a valid legacy cookie for a real per-device session (called on page loads, where a cookie can be set).
        Idempotent per legacy cookie while that session lives: parallel loads get the same token, not one session each."""
        with self._lock:
            digest = _hash(legacy_cookie) if legacy_cookie else ""
            known = self._upgraded.get(digest)
            if known and any(hmac.compare_digest(str(r.get("hash", "")), _hash(known)) for r in self._sessions().values()):
                return known
            token = self._new_session(user_agent)
            if digest:
                self._upgraded[digest] = token
            return token

    def list(self) -> list[dict]:
        return [{"id": sid, "label": r.get("label", "Device"), "created_at": r.get("created_at"), "last_seen_at": r.get("last_seen_at")} for sid, r in self._sessions().items()]

    def revoke(self, sid: str) -> bool:
        with self._lock:
            sessions = self._sessions()
            found = sessions.pop(sid, None) is not None
            if found:
                self._store(sessions)
            return found

    def revoke_all(self) -> None:
        with self._lock:
            self._store({})
            self._pairing = None
            self._save(TOKEN_KEY, None)


def request_is_secure(request: Request) -> bool:
    return request.url.scheme == "https" or request.headers.get("x-forwarded-proto", "").split(",")[0].strip().lower() == "https"


READ_ONLY_META = '<meta name="cadence-mode" content="read-only" />'
TAILSCALE_APP_CLI = "/Applications/Tailscale.app/Contents/MacOS/Tailscale"
SECURITY_HEADERS = [
    (b"x-content-type-options", b"nosniff"),
    (b"referrer-policy", b"no-referrer"),
    (b"x-frame-options", b"DENY"),
]


def _page(title: str, body: str, status: int) -> HTMLResponse:
    html = f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>Cadence</title>
<style>body{{margin:0;min-height:100dvh;display:grid;place-items:center;background:#0b0b0c;color:#ecebe6;
font:16px/1.5 -apple-system,system-ui,sans-serif;padding:24px}}h1{{font-weight:500;font-size:28px;margin:0 0 8px}}
p{{color:#8d8a82;max-width:32ch}}</style></head><body><main><h1>{escape(title)}</h1><p>{escape(body)}</p></main></body></html>"""
    return HTMLResponse(html, status_code=status, headers={"Cache-Control": "no-store"})


class ShareGate:
    """Authenticates every request by per-device session cookie, allows reads plus a strict write allowlist, and serves the built web app."""

    def __init__(self, api: ASGIApp, auth: ShareAuth, web_dir: Path, enabled: Callable[[], bool] = lambda: True):
        self.api, self.auth, self.enabled, self.web_dir = api, auth, enabled, web_dir.resolve()

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            return
        secure_send = self._secure(send)
        response = self._route(Request(scope))
        if response is not None:
            await response(scope, receive, secure_send)
            return
        # Authorised request: the inner app only trusts loopback hosts and same-origin writes.
        headers = [(k, v) for k, v in scope["headers"] if k not in (b"host", b"origin")] + [(b"host", b"127.0.0.1")]
        await self.api({**scope, "headers": headers}, receive, secure_send)

    @staticmethod
    def _secure(send: Send) -> Send:
        async def wrapped(message: Message) -> None:
            if message["type"] == "http.response.start":
                message = {**message, "headers": [*message.get("headers", []), *SECURITY_HEADERS]}
            await send(message)

        return wrapped

    @staticmethod
    def _set_session(response: Response, token: str, secure: bool) -> None:
        response.set_cookie(SECURE_COOKIE if secure else COOKIE, token, max_age=COOKIE_MAX_AGE, httponly=True, samesite="lax", path="/", secure=secure)
        if secure:
            response.delete_cookie(COOKIE, path="/")  # an old plain cookie must not shadow the __Host- one

    def _route(self, request: Request) -> Response | None:
        path = request.url.path
        if not self.enabled():
            return _page("Sharing is off", "Turn on phone access in Cadence → Settings on your Mac.", 503)
        secure = request_is_secure(request)
        agent = request.headers.get("user-agent", "")
        if path == "/pair":
            client = request.client.host if request.client else "?"
            token, wait = self.auth.try_pair(request.query_params.get("key", ""), client, agent)
            if token is None and wait:
                return PlainTextResponse("Too many attempts. Try again later.", status_code=429, headers={"Retry-After": str(wait)})
            if token is None:
                return _page("Pairing code expired", "Scan a fresh QR code in Cadence → Settings on your Mac. Each code works once.", 403)
            response = RedirectResponse("/", status_code=303)
            self._set_session(response, token, secure)
            return response
        cookie = request.cookies.get(SECURE_COOKIE if secure else COOKIE, "") or request.cookies.get(COOKIE, "")
        upgraded = None
        if self.auth.check(cookie) is None:
            if not self.auth.legacy_valid(cookie):
                return _page("Not paired", "This phone isn't paired, or its pairing expired or was removed. Scan a fresh QR code in Cadence → Settings on your Mac.", 401)
            if request.method == "GET" and path in ("/", "/index.html"):
                upgraded = self.auth.upgrade_legacy(agent, cookie)
        if request.method not in ("GET", "HEAD") and not phone_may_write(request.method, path):
            return PlainTextResponse("This device has read-only access.", status_code=405)  # only after authentication: strangers learn nothing about the allowlist
        if path.startswith("/api/"):
            if path.startswith(BLOCKED_API):
                return JSONResponse({"detail": "Not available on shared devices"}, status_code=404)
            return None
        response = self._static(path)
        if upgraded:
            self._set_session(response, upgraded, secure)
        return response

    def _static(self, path: str) -> Response:
        rel = path.lstrip("/")
        if rel:
            target = (self.web_dir / rel).resolve()
            if self.web_dir in target.parents and target.is_file():
                cache = "public, max-age=31536000, immutable" if rel.startswith("assets/") else "no-cache"
                return FileResponse(target, headers={"Cache-Control": cache})
        index = self.web_dir / "index.html"
        if not index.is_file():
            return _page("Web app not built", "Run `npm run build` in app/web on your Mac.", 503)
        html = index.read_text(encoding="utf-8").replace("<head>", f"<head>\n    {READ_ONLY_META}", 1)
        return HTMLResponse(html, headers={"Cache-Control": "no-cache"})


def tailscale_url(port: int) -> str | None:
    """HTTPS address when `tailscale serve` proxies to the share port."""
    cli = next((p for p in (shutil.which("tailscale"), TAILSCALE_APP_CLI) if p and Path(p).is_file()), None)
    if cli is None:
        return None
    try:
        # The macOS app binary only acts as a CLI when TERM is set; services launched by launchd have none.
        env = {**os.environ, "TERM": os.environ.get("TERM", "dumb")}
        result = subprocess.run([cli, "serve", "status", "--json"], capture_output=True, text=True, timeout=5, check=False, env=env)
        config = json.loads(result.stdout or "{}")
    except (OSError, subprocess.SubprocessError, ValueError):
        return None
    for hostport, web in (config.get("Web") or {}).items():
        for handler in (web.get("Handlers") or {}).values():
            if str(handler.get("Proxy", "")).rstrip("/").endswith(f":{port}"):
                host, _, listen = hostport.rpartition(":")
                return f"https://{host}" + ("" if listen == "443" else f":{listen}")
    return None


def lan_addresses() -> list[str]:
    hosts: list[str] = []
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("10.255.255.255", 1))  # UDP connect sends nothing; it only picks the outbound interface
            ip = s.getsockname()[0]
            if not ip.startswith("127."):
                hosts.append(ip)
    except OSError:
        pass
    name = socket.gethostname()
    if name and name != "localhost":
        hosts.append(name if name.endswith(".local") else f"{name}.local")
    return hosts


class ShareServer:
    def __init__(self, api: ASGIApp, factory: sessionmaker, web_dir: Path, port: int, host: str = "0.0.0.0"):
        self.factory, self.web_dir, self.port, self.host = factory, web_dir, port, host
        self.auth = ShareAuth(self._setting, self._save)
        self.gate = ShareGate(api, self.auth, web_dir, lambda: self.running)
        self._server: uvicorn.Server | None = None
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()

    @property
    def running(self) -> bool:
        return self._server is not None and self._server.started and not self._server.should_exit

    def _setting(self, key: str) -> str | None:
        with self.factory() as session:
            row = session.get(AppSetting, key)
            return row.value if row else None

    def _save(self, key: str, value: str | None) -> None:
        with self.factory() as session, session.begin():
            row = session.get(AppSetting, key)
            if value is None:
                if row:
                    session.delete(row)
            elif row:
                row.value = value
            else:
                session.add(AppSetting(key=key, value=value))

    def start(self) -> None:
        with self._lock:
            if self.running:
                return
            if not (self.web_dir / "index.html").is_file():
                raise RuntimeError("The web app isn't built yet. Run `npm run build` in app/web.")
            config = uvicorn.Config(self.gate, host=self.host, port=self.port, access_log=False, log_level="warning", lifespan="off")
            self._server = uvicorn.Server(config)
            self._thread = threading.Thread(target=self._server.run, daemon=True, name="share-server")
            self._thread.start()
            deadline = time.monotonic() + 5
            while not self._server.started and self._thread.is_alive() and time.monotonic() < deadline:
                time.sleep(0.05)
            if not self._server.started:
                self._server.should_exit = True
                self._server = None
                raise RuntimeError(f"Couldn't listen on port {self.port}; is something else using it?")
            self._save(ENABLED_KEY, "1")

    def stop(self, remember: bool = True) -> None:
        with self._lock:
            if self._server is not None:
                self._server.should_exit = True
                if self._thread:
                    self._thread.join(timeout=5)
            self._server = self._thread = None
            if remember:
                self._save(ENABLED_KEY, None)

    def reset(self) -> None:
        """Revokes every paired phone and invalidates the pairing key."""
        self.auth.revoke_all()

    def revoke(self, session_id: str) -> bool:
        return self.auth.revoke(session_id)

    def resume(self) -> None:
        if self._setting(ENABLED_KEY) == "1":
            try:
                self.start()
            except RuntimeError as exc:
                log.warning("Phone sharing not resumed: %s", exc)

    def status(self) -> dict:
        built = self.web_dir / "index.html"
        out = {
            "running": self.running,
            "port": self.port,
            "host": self.host,
            "web_built_at": built.stat().st_mtime if built.is_file() else None,
            "urls": [],
            "pair_url": None,
            "pair_expires_in_s": None,
            "qr": None,
            "secure": False,
            # True when the only way in is plain http on the local network: anyone on that network can watch the traffic.
            "insecure_lan": False,
            "sessions": self.auth.list(),
        }
        if self.running:
            out["urls"] = [f"http://{h}:{self.port}" for h in lan_addresses()]
            if remote := tailscale_url(self.port):
                out["urls"].insert(0, remote)
            out["secure"] = bool(remote)
            out["insecure_lan"] = not remote
            if out["urls"]:
                key, expires = self.auth.pairing_key()
                out["pair_url"] = f"{out['urls'][0]}/pair?key={key}"
                out["pair_expires_in_s"] = max(0, int(expires - time.time()))
                qr = segno.make(out["pair_url"], error="m")
                out["qr"] = [[1 if cell else 0 for cell in row] for row in qr.matrix]
        return out
