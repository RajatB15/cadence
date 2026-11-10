"""Claude connector: a read-only remote MCP server, so the Claude app (web, desktop, iPhone) can look at your Cadence data.

Claude reaches the phone share server's public HTTPS address from Anthropic's cloud, so this lives on that server and
has its own sign-in, separate from the paired-phone cookie. Nothing here can change anything: every tool is a GET on an
existing endpoint, called inside this process, and the OAuth flow only ever hands out the right to call those tools.

Sign-in is OAuth 2.1 as the claude.ai custom-connector flow expects it (https://support.claude.com/en/articles/11503834):
protected-resource and authorization-server metadata (RFC 9728, RFC 8414), dynamic client registration (RFC 7591) limited
to Claude's own callback URLs, authorization code with PKCE S256 (RFC 7636), refresh tokens. The one thing a stranger
cannot do is approve a connection: the approval page wants a short single-use code that is shown only in Cadence's
Settings (reachable only from your own machine), expires in 10 minutes, and wrong guesses are throttled hard. Only the
SHA-256 of each refresh token is stored, and each connection can be revoked alone.

MCP over Streamable HTTP (https://modelcontextprotocol.io/specification/2025-06-18/basic/transports): one JSON-RPC
message per POST, answered with a JSON body; no server-initiated streams.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import re
import secrets
import threading
import time
from collections.abc import Callable
from datetime import datetime, timezone
from urllib.parse import parse_qs, urlencode

import httpx
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse, PlainTextResponse, RedirectResponse, Response
from starlette.types import ASGIApp, Receive, Scope, Send

log = logging.getLogger(__name__)

PATHS = ("/.well-known/oauth-protected-resource", "/.well-known/oauth-authorization-server", "/oauth/", "/mcp")
ALLOWED_REDIRECTS = ("https://claude.ai/api/mcp/auth_callback", "https://claude.com/api/mcp/auth_callback")
SESSIONS_KEY, ENABLED_KEY = "connector_sessions", "connector_enabled"
APPROVAL_TTL_S, CODE_TTL_S, ACCESS_TTL_S, REFRESH_TTL_S = 10 * 60, 5 * 60, 60 * 60, 90 * 86400
MAX_SESSIONS = 10
FAIL_FREE, FAIL_MAX_BLOCK_S = 3, 30 * 60
GLOBAL_FAIL_WINDOW_S, GLOBAL_FAIL_MAX = 10 * 60, 30
MAX_BODY = 64 * 1024
MAX_RESULT_CHARS = 40_000
PROTOCOLS = ("2025-06-18", "2025-03-26", "2024-11-05")
APPROVAL_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # no 0/O/1/I: typed from a screen

INSTRUCTIONS = (
    "Cadence is one person's private training and health coach, built on their Garmin data. Everything is read-only. "
    "Body-composition values are formula estimates, never measurements. Food calories are estimates with a range, and "
    "a day with nothing logged is missing data, not zero. Analytics state their sample size and uncertainty; repeat "
    "that caution, make no medical or causal claims, and say so when a tool returns little or no data."
)

_DAY = r"\d{4}-\d{2}-\d{2}"
# name -> (description, path template, {param: (kind, required, pattern|max, where)}); every tool is a GET.
TOOLS: dict[str, tuple[str, str, dict[str, tuple]]] = {
    "today": ("Today at a glance: readiness, today's session, energy burned vs eaten, sleep and the day's coach notes.", "/api/overview", {}),
    "day": ("Everything recorded for one day (sleep, recovery, activities, food, notes).", "/api/days/{day}", {"day": ("str", True, _DAY, "path")}),
    "recent_activities": ("Recent workouts, newest first, with distance, time, pace/power and heart rate.", "/api/activities",
                          {"limit": ("int", False, 20, "query"), "family": ("str", False, r"[a-z_]{1,16}", "query")}),
    "activity": ("One workout in detail, by its id from recent_activities.", "/api/activities/{activity_id}", {"activity_id": ("str", True, r"\d{1,20}", "path")}),
    "training_summary": ("Training volume and trends across weeks.", "/api/trends/training", {}),
    "review": ("The weekly or monthly review of training, sleep and fitness.", "/api/reviews/{kind}", {"kind": ("str", True, r"week|month", "path")}),
    "weight": ("Weight history and trend, with the body-composition estimates (formula-based, not measured).", "/api/weight", {}),
    "food": ("What was eaten on a day, with calorie ranges, protein and the day's targets.", "/api/food", {"day": ("str", False, _DAY, "query")}),
    "plan": ("The planned sessions coming up.", "/api/planner", {}),
    "goals": ("Goals (races, distances, weight) and whether each looks feasible.", "/api/goals", {}),
    "time_off": ("Travel, illness, injury and holiday periods and how the plan eases around them.", "/api/time-off", {}),
    "score": ("The overall fitness score and the biggest gaps.", "/api/score", {}),
    "outcomes": ("The last 12 weeks compared with the 12 before.", "/api/outcomes", {}),
    "metric": ("History of one metric (for example resting_hr, hrv, vo2max, sleep_hours).", "/api/metrics/{metric}", {"metric": ("str", True, r"[a-z0-9_]{1,40}", "path")}),
}


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def _b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")


def _tool_schema(name: str) -> dict:
    description, _, params = TOOLS[name]
    props, required = {}, []
    for pname, (kind, req, rule, _where) in params.items():
        spec: dict = {"type": "integer" if kind == "int" else "string"}
        if kind == "int":
            spec.update(minimum=1, maximum=rule)
        else:
            spec["pattern"] = f"^(?:{rule})$"
        props[pname] = spec
        if req:
            required.append(pname)
    return {"name": name, "description": description, "inputSchema": {"type": "object", "properties": props, "required": required, "additionalProperties": False},
            "annotations": {"readOnlyHint": True, "destructiveHint": False, "openWorldHint": False}}


class ConnectorAuth:
    """Approval code, registered clients, authorization codes, access and refresh tokens."""

    def __init__(self, load: Callable[[str], str | None], save: Callable[[str, str | None], None], clock: Callable[[], float] = time.time):
        self._load, self._save, self._clock = load, save, clock
        self._lock = threading.Lock()
        self._approval: tuple[str, float] | None = None
        self._clients: dict[str, dict] = {}
        self._codes: dict[str, dict] = {}
        self._access: dict[str, tuple[str, float]] = {}  # sha256(access token) -> (session id, expiry)
        self._fails: dict[str, tuple[int, float]] = {}
        self._global_fails: list[float] = []

    # --- switch
    def enabled(self) -> bool:
        return self._load(ENABLED_KEY) == "1"

    def set_enabled(self, on: bool) -> None:
        self._save(ENABLED_KEY, "1" if on else None)
        if not on:
            self.revoke_all()

    # --- approval code (shown in Settings only)
    def approval_code(self) -> tuple[str, float]:
        with self._lock:
            now = self._clock()
            if self._approval is None or self._approval[1] <= now:
                self._approval = ("".join(secrets.choice(APPROVAL_ALPHABET) for _ in range(10)), now + APPROVAL_TTL_S)
            return self._approval

    def rotate_approval(self) -> None:
        with self._lock:
            self._approval = None

    # --- throttle for wrong approval codes
    def blocked_for(self, client: str) -> int:
        return max(0, int(self._fails.get(client, (0, 0.0))[1] - self._clock() + 0.999))

    def _fail(self, client: str) -> None:
        count = self._fails.get(client, (0, 0.0))[0] + 1
        delay = min(FAIL_MAX_BLOCK_S, 2 ** (count - FAIL_FREE) * 30) if count > FAIL_FREE else 0
        self._global_fails.append(self._clock())
        if len(self._fails) > 1000:
            self._fails.clear()
        self._fails[client] = (count, self._clock() + delay)
        log.warning("Failed connector approval #%d from %s (blocked for %ds)", count, client, delay)

    def _global_blocked(self) -> bool:
        now = self._clock()
        self._global_fails = [t for t in self._global_fails if now - t < GLOBAL_FAIL_WINDOW_S]
        return len(self._global_fails) >= GLOBAL_FAIL_MAX

    # --- dynamic client registration
    def register(self, redirect_uris: list[str], name: str) -> dict | None:
        """A client only for Claude's own callback URLs; anything else is refused."""
        if not redirect_uris or any(u not in ALLOWED_REDIRECTS for u in redirect_uris):
            return None
        with self._lock:
            if len(self._clients) > 200:
                self._clients.clear()
            cid = "cadence-" + secrets.token_urlsafe(16)
            self._clients[cid] = {"redirect_uris": list(redirect_uris), "name": (name or "Claude")[:60]}
        return {"client_id": cid, "client_name": self._clients[cid]["name"], "redirect_uris": redirect_uris, "token_endpoint_auth_method": "none",
                "grant_types": ["authorization_code", "refresh_token"], "response_types": ["code"]}

    def client(self, cid: str) -> dict | None:
        return self._clients.get(cid)

    # --- approval -> authorization code
    def approve(self, client_id: str, redirect_uri: str, challenge: str, entered: str, who: str) -> tuple[str | None, int]:
        """(authorization code, 0) for the right approval code; (None, seconds to wait) when throttled; (None, 0) for a miss."""
        with self._lock:
            now = self._clock()
            cur = self._approval
            entered = re.sub(r"[\s-]", "", entered).upper()
            ok = cur is not None and cur[1] > now and bool(entered) and hmac.compare_digest(entered.encode(), cur[0].encode())
            if ok:
                self._approval = None  # single use
                self._fails.pop(who, None)
                code = secrets.token_urlsafe(32)
                self._codes[code] = {"client_id": client_id, "redirect_uri": redirect_uri, "challenge": challenge, "expires": now + CODE_TTL_S}
                return code, 0
            if wait := self.blocked_for(who):
                return None, wait
            if self._global_blocked():
                return None, 60
            self._fail(who)
            return None, 0

    # --- token endpoint
    def exchange(self, code: str, client_id: str, redirect_uri: str, verifier: str, label: str) -> dict | None:
        with self._lock:
            grant = self._codes.pop(code, None)
            now = self._clock()
            if not grant or grant["expires"] <= now or grant["client_id"] != client_id or grant["redirect_uri"] != redirect_uri:
                return None
            if not hmac.compare_digest(_b64url(hashlib.sha256(verifier.encode()).digest()), grant["challenge"]):
                return None
            sessions = self._sessions()
            sid = secrets.token_hex(6)
            sessions[sid] = {"label": label[:60] or "Claude", "created_at": _now_iso(), "last_used_at": _now_iso(), "refresh": "", "expires": 0.0}
            while len(sessions) > MAX_SESSIONS:
                sessions.pop(min(sessions, key=lambda k: sessions[k].get("last_used_at", "")))
            return self._issue(sessions, sid, now)

    def refresh(self, refresh_token: str, client_id: str) -> dict | None:
        with self._lock:
            digest, now = _sha(refresh_token), self._clock()
            sessions = self._sessions()
            for sid, rec in sessions.items():
                if rec.get("refresh") and hmac.compare_digest(rec["refresh"], digest) and rec.get("expires", 0) > now:
                    return self._issue(sessions, sid, now)
            return None

    def _issue(self, sessions: dict, sid: str, now: float) -> dict:
        access, refresh = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
        sessions[sid].update(refresh=_sha(refresh), expires=now + REFRESH_TTL_S, last_used_at=_now_iso())
        self._store(sessions)
        self._access = {k: v for k, v in self._access.items() if v[1] > now}
        self._access[_sha(access)] = (sid, now + ACCESS_TTL_S)
        return {"access_token": access, "token_type": "Bearer", "expires_in": ACCESS_TTL_S, "refresh_token": refresh}

    def check(self, access: str) -> str | None:
        """Session id for a live access token, else None. A revoked session's tokens stop working at once."""
        hit = self._access.get(_sha(access)) if access else None
        if hit is None or hit[1] <= self._clock() or hit[0] not in self._sessions():
            return None
        return hit[0]

    # --- sessions
    def _sessions(self) -> dict[str, dict]:
        try:
            data = json.loads(self._load(SESSIONS_KEY) or "{}")
        except ValueError:
            return {}
        return data if isinstance(data, dict) else {}

    def _store(self, sessions: dict) -> None:
        self._save(SESSIONS_KEY, json.dumps(sessions))

    def list(self) -> list[dict]:
        return [{"id": sid, "label": r.get("label", "Claude"), "created_at": r.get("created_at"), "last_used_at": r.get("last_used_at")} for sid, r in self._sessions().items()]

    def revoke(self, sid: str) -> bool:
        with self._lock:
            sessions = self._sessions()
            found = sessions.pop(sid, None) is not None
            if found:
                self._store(sessions)
                self._access = {k: v for k, v in self._access.items() if v[0] != sid}
            return found

    def revoke_all(self) -> None:
        with self._lock:
            self._store({})
            self._access.clear()
            self._approval = None


async def _form(request: Request) -> dict[str, str]:
    """An application/x-www-form-urlencoded body (all the OAuth endpoints and the approval page post this), first value of each field."""
    body = (await request.body())[:MAX_BODY].decode("utf-8", "replace")
    return {k: v[0] for k, v in parse_qs(body, keep_blank_values=True).items()}


def _page(title: str, body: str, status: int = 200, form: str = "") -> HTMLResponse:
    from html import escape

    html = f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Cadence</title><style>body{{margin:0;min-height:100dvh;display:grid;place-items:center;background:#0b0b0c;color:#ecebe6;font:16px/1.5 -apple-system,system-ui,sans-serif;padding:24px}}
main{{max-width:34ch}}h1{{font-weight:500;font-size:26px;margin:0 0 8px}}p{{color:#8d8a82}}input{{font:inherit;font-size:22px;letter-spacing:.2em;text-transform:uppercase;width:100%;box-sizing:border-box;padding:12px;margin:12px 0;border-radius:12px;border:1px solid #3a3a3d;background:#161618;color:#ecebe6}}
button{{font:inherit;padding:12px 20px;border-radius:999px;border:0;background:#fbe9d0;color:#111;font-weight:600;cursor:pointer}}</style></head>
<body><main><h1>{escape(title)}</h1><p>{escape(body)}</p>{form}</main></body></html>"""
    return HTMLResponse(html, status_code=status, headers={"Cache-Control": "no-store", "X-Frame-Options": "DENY", "Referrer-Policy": "no-referrer"})


class Connector:
    """The ASGI app for the connector's paths. `api` is the main Cadence app, called in-process with GET only."""

    def __init__(self, api: ASGIApp, auth: ConnectorAuth, public_url: Callable[[], str | None] = lambda: None):
        self.api, self.auth, self.public_url = api, auth, public_url

    @staticmethod
    def handles(path: str) -> bool:
        return path == "/mcp" or path.startswith(("/.well-known/oauth-protected-resource", "/.well-known/oauth-authorization-server", "/oauth/"))

    def base(self, request: Request) -> str:
        if url := self.public_url():
            return url.rstrip("/")
        proto = request.headers.get("x-forwarded-proto", request.url.scheme).split(",")[0].strip()
        return f"{proto}://{request.headers.get('host', request.url.netloc)}"

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        request = Request(scope, receive)
        response = await self._route(request) if self.auth.enabled() else JSONResponse({"error": "not_found"}, status_code=404)
        await response(scope, receive, send)

    async def _route(self, request: Request) -> Response:
        path, method = request.url.path, request.method
        if path.startswith("/.well-known/oauth-protected-resource") and method == "GET":
            base = self.base(request)
            return JSONResponse({"resource": f"{base}/mcp", "authorization_servers": [base], "bearer_methods_supported": ["header"]})
        if path.startswith("/.well-known/oauth-authorization-server") and method == "GET":
            b = self.base(request)
            return JSONResponse({"issuer": b, "authorization_endpoint": f"{b}/oauth/authorize", "token_endpoint": f"{b}/oauth/token",
                                 "registration_endpoint": f"{b}/oauth/register", "response_types_supported": ["code"],
                                 "grant_types_supported": ["authorization_code", "refresh_token"], "code_challenge_methods_supported": ["S256"],
                                 "token_endpoint_auth_methods_supported": ["none"]})
        if path == "/oauth/register" and method == "POST":
            return await self._register(request)
        if path == "/oauth/authorize" and method in ("GET", "POST"):
            return await self._authorize(request)
        if path == "/oauth/token" and method == "POST":
            return await self._token(request)
        if path == "/mcp":
            return await self._mcp(request) if method == "POST" else PlainTextResponse("POST only", status_code=405, headers={"Allow": "POST"})
        return JSONResponse({"error": "not_found"}, status_code=404)

    # --- OAuth
    async def _register(self, request: Request) -> Response:
        try:
            body = json.loads((await request.body())[:MAX_BODY] or b"{}")
        except ValueError:
            body = None
        uris = body.get("redirect_uris") if isinstance(body, dict) else None
        reg = self.auth.register([u for u in uris if isinstance(u, str)] if isinstance(uris, list) else [], str(body.get("client_name", "")) if isinstance(body, dict) else "")
        if reg is None:
            return JSONResponse({"error": "invalid_redirect_uri", "error_description": "Only Claude's own callback URLs are accepted."}, status_code=400)
        return JSONResponse(reg, status_code=201)

    def _authorize_params(self, params) -> tuple[dict | None, str]:
        client = self.auth.client(params.get("client_id", ""))
        redirect = params.get("redirect_uri", "")
        if client is None or redirect not in client["redirect_uris"]:
            return None, "This connection request is not recognised. Start again from Claude."
        if params.get("response_type") != "code" or params.get("code_challenge_method") != "S256" or not re.fullmatch(r"[A-Za-z0-9_-]{43,128}", params.get("code_challenge", "")):
            return None, "This connection request is incomplete. Start again from Claude."
        return client, ""

    async def _authorize(self, request: Request) -> Response:
        params = dict(request.query_params)
        form_data: dict = {}
        if request.method == "POST":
            form_data = await _form(request)
            params = {**params, **{k: form_data[k] for k in ("client_id", "redirect_uri", "response_type", "code_challenge", "code_challenge_method", "state") if k in form_data}}
        client, problem = self._authorize_params(params)
        if client is None:
            return _page("Can't connect", problem, 400)
        from html import escape

        hidden = "".join(f'<input type="hidden" name="{k}" value="{escape(params.get(k, ""), quote=True)}" style="display:none">'
                         for k in ("client_id", "redirect_uri", "response_type", "code_challenge", "code_challenge_method", "state"))
        form = (f'<form method="post" action="/oauth/authorize">{hidden}<input name="approval" autocomplete="off" autocapitalize="characters" '
                f'inputmode="text" maxlength="16" placeholder="CODE" aria-label="Approval code" autofocus><button type="submit">Approve</button></form>')
        intro = f"{client['name']} wants to read your Cadence data (read-only). Enter the approval code shown in Cadence → Settings → Claude."
        if request.method == "GET":
            return _page("Connect Claude", intro, form=form)
        who = request.client.host if request.client else "?"
        code, wait = self.auth.approve(params["client_id"], params["redirect_uri"], params["code_challenge"], form_data.get("approval", ""), who)
        if code is None and wait:
            return _page("Too many tries", "Wait a while, then start again from Claude.", 429)
        if code is None:
            return _page("Wrong or expired code", intro, 403, form)
        query = {"code": code}
        if params.get("state"):
            query["state"] = params["state"]
        return RedirectResponse(f"{params['redirect_uri']}?{urlencode(query)}", status_code=303, headers={"Cache-Control": "no-store"})

    async def _token(self, request: Request) -> Response:
        headers = {"Cache-Control": "no-store", "Pragma": "no-cache"}
        form = await _form(request)
        grant = form.get("grant_type")
        client_id = form.get("client_id", "")
        client = self.auth.client(client_id)
        result = None
        if grant == "authorization_code":
            result = self.auth.exchange(form.get("code", ""), client_id, form.get("redirect_uri", ""), form.get("code_verifier", ""), client["name"] if client else "Claude")
        elif grant == "refresh_token":
            result = self.auth.refresh(form.get("refresh_token", ""), client_id)
        if result is None:
            return JSONResponse({"error": "invalid_grant"}, status_code=400, headers=headers)
        return JSONResponse(result, headers=headers)

    # --- MCP
    def _unauthorized(self, request: Request) -> Response:
        meta = f"{self.base(request)}/.well-known/oauth-protected-resource"
        return JSONResponse({"error": "unauthorized"}, status_code=401, headers={"WWW-Authenticate": f'Bearer resource_metadata="{meta}"'})

    async def _mcp(self, request: Request) -> Response:
        auth = request.headers.get("authorization", "")
        if not auth.lower().startswith("bearer ") or self.auth.check(auth[7:].strip()) is None:
            return self._unauthorized(request)
        raw = await request.body()
        if len(raw) > MAX_BODY:
            return JSONResponse({"error": "too_large"}, status_code=413)
        try:
            message = json.loads(raw)
        except ValueError:
            return JSONResponse({"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "Parse error"}}, status_code=400)
        batch = message if isinstance(message, list) else [message]
        replies = [r for r in [await self._handle(m) for m in batch] if r is not None]
        if not replies:
            return Response(status_code=202)
        return JSONResponse(replies if isinstance(message, list) else replies[0])

    async def _handle(self, msg: object) -> dict | None:
        if not isinstance(msg, dict) or msg.get("jsonrpc") != "2.0" or not isinstance(msg.get("method"), str):
            return {"jsonrpc": "2.0", "id": None, "error": {"code": -32600, "message": "Invalid request"}}
        method, mid, params = msg["method"], msg.get("id"), msg.get("params") if isinstance(msg.get("params"), dict) else {}
        if "id" not in msg:
            return None  # a notification (initialized, cancelled): nothing to answer
        ok = lambda result: {"jsonrpc": "2.0", "id": mid, "result": result}  # noqa: E731
        err = lambda code, text: {"jsonrpc": "2.0", "id": mid, "error": {"code": code, "message": text}}  # noqa: E731
        if method == "initialize":
            asked = params.get("protocolVersion")
            return ok({"protocolVersion": asked if asked in PROTOCOLS else PROTOCOLS[0], "capabilities": {"tools": {"listChanged": False}},
                       "serverInfo": {"name": "cadence", "title": "Cadence", "version": "1.0"}, "instructions": INSTRUCTIONS})
        if method == "ping":
            return ok({})
        if method == "tools/list":
            return ok({"tools": [_tool_schema(n) for n in TOOLS]})
        if method == "tools/call":
            name = params.get("name")
            if name not in TOOLS:
                return err(-32602, "Unknown tool")
            return ok(await self._call(name, params.get("arguments") if isinstance(params.get("arguments"), dict) else {}))
        return err(-32601, "Method not found")

    async def _call(self, name: str, args: dict) -> dict:
        _, template, params = TOOLS[name]
        path_vals, query = {}, {}
        for pname, (kind, required, rule, where) in params.items():
            value = args.get(pname)
            if value is None:
                if required:
                    return _result(f"Missing argument: {pname}", True)
                continue
            if kind == "int":
                if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= rule:
                    return _result(f"{pname} must be a whole number from 1 to {rule}", True)
            elif not isinstance(value, str) or not re.fullmatch(rule, value):
                return _result(f"{pname} is not in the expected format", True)
            (path_vals if where == "path" else query)[pname] = value
        if set(args) - set(params):
            return _result("Unexpected argument: " + ", ".join(sorted(set(args) - set(params))), True)
        try:
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=self.api), base_url="http://127.0.0.1", timeout=30) as client:
                response = await client.get(template.format(**path_vals), params=query, headers={"X-Cadence-Request": "1"})
        except httpx.HTTPError:
            return _result("Cadence couldn't be reached just now.", True)
        if response.status_code == 404:
            return _result("Nothing found for that request.", True)
        if response.status_code != 200:
            return _result(f"Cadence answered with an error ({response.status_code}).", True)
        try:
            text = json.dumps(response.json(), separators=(",", ":"), ensure_ascii=False)
        except ValueError:
            return _result("Cadence returned something unreadable.", True)
        if len(text) > MAX_RESULT_CHARS:
            text = text[:MAX_RESULT_CHARS] + f'… [cut: the full answer was {len(text)} characters; ask for a narrower view]'
        return _result(text, False)


def _result(text: str, is_error: bool) -> dict:
    return {"content": [{"type": "text", "text": text}], "isError": is_error}
