"""Read-only phone access over the local network, paired with a QR code shown on the Mac."""

from __future__ import annotations

import hmac
import json
import logging
import os
import secrets
import shutil
import socket
import subprocess
import threading
import time
from collections.abc import Callable
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
TOKEN_KEY, ENABLED_KEY = "share_token", "share_enabled"
COOKIE_MAX_AGE = 180 * 86400
BLOCKED_API = ("/api/share",)
# The only writes a paired phone may make: its own notifications and an on-demand Garmin refresh.
PHONE_WRITES = {"/api/push/subscribe", "/api/push/unsubscribe", "/api/push/test", "/api/push/prefs", "/api/garmin/sync"}
# The journal check-in and weight logging happen on the phone, and the weather toggle and body profile are plain preferences, so those routes accept writes from paired devices too.
PHONE_WRITE_PREFIXES = ("/api/journal/", "/api/strength/", "/api/planner", "/api/weight/entries", "/api/settings/weather", "/api/settings/profile")
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
    """Authenticates every request by pairing cookie, allows reads only, and serves the built web app."""

    def __init__(self, api: ASGIApp, token: Callable[[], str | None], web_dir: Path):
        self.api, self.token, self.web_dir = api, token, web_dir.resolve()

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

    def _route(self, request: Request) -> Response | None:
        path = request.url.path
        if request.method not in ("GET", "HEAD") and path not in PHONE_WRITES and not path.startswith(PHONE_WRITE_PREFIXES):
            return PlainTextResponse("This device has read-only access.", status_code=405)
        token = self.token()
        if not token:
            return _page("Sharing is off", "Turn on phone access in Cadence → Settings on your Mac.", 503)
        if path == "/pair":
            if not hmac.compare_digest(request.query_params.get("key", "").encode(), token.encode()):
                return _page("Pairing code expired", "Scan the current QR code in Cadence → Settings on your Mac.", 403)
            response = RedirectResponse("/", status_code=303)
            response.set_cookie(COOKIE, token, max_age=COOKIE_MAX_AGE, httponly=True, samesite="lax", path="/")
            return response
        if not hmac.compare_digest(request.cookies.get(COOKIE, "").encode(), token.encode()):
            return _page("Not paired", "Scan the QR code in Cadence → Settings on your Mac to open your data here.", 401)
        if path.startswith("/api/"):
            if path.startswith(BLOCKED_API):
                return JSONResponse({"detail": "Not available on shared devices"}, status_code=404)
            return None
        return self._static(path)

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
        self.gate = ShareGate(api, lambda: self._token if self.running else None, web_dir)
        self._token: str | None = None
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

    def token(self) -> str:
        if self._token is None:
            self._token = self._setting(TOKEN_KEY)
            if self._token is None:
                self._token = secrets.token_urlsafe(32)
                self._save(TOKEN_KEY, self._token)
        return self._token

    def start(self) -> None:
        with self._lock:
            if self.running:
                return
            if not (self.web_dir / "index.html").is_file():
                raise RuntimeError("The web app isn't built yet. Run `npm run build` in app/web.")
            self.token()
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
        """New pairing key; every phone paired with the old one loses access."""
        self._token = secrets.token_urlsafe(32)
        self._save(TOKEN_KEY, self._token)

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
            "web_built_at": built.stat().st_mtime if built.is_file() else None,
            "urls": [],
            "pair_url": None,
            "qr": None,
            "secure": False,
        }
        if self.running:
            out["urls"] = [f"http://{h}:{self.port}" for h in lan_addresses()]
            if remote := tailscale_url(self.port):
                out["urls"].insert(0, remote)
            out["secure"] = bool(remote)
            if out["urls"]:
                out["pair_url"] = f"{out['urls'][0]}/pair?key={self.token()}"
                qr = segno.make(out["pair_url"], error="m")
                out["qr"] = [[1 if cell else 0 for cell in row] for row in qr.matrix]
        return out
