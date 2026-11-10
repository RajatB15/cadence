import base64
import hashlib
import json
import re

import pytest
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from cadence_app import connector as C

REDIRECT = "https://claude.ai/api/mcp/auth_callback"
VERIFIER = "v" * 64
CHALLENGE = base64.urlsafe_b64encode(hashlib.sha256(VERIFIER.encode()).digest()).rstrip(b"=").decode()
SEEN: list[tuple[str, str]] = []


def stub_api():
    async def anything(request):
        SEEN.append((request.method, request.url.path + ("?" + request.url.query if request.url.query else "")))
        if request.url.path == "/api/days/2000-01-01":
            return JSONResponse({"detail": "none"}, status_code=404)
        if request.url.path == "/api/score":
            return JSONResponse({"blob": "x" * (C.MAX_RESULT_CHARS + 500)})
        return JSONResponse({"ok": True, "path": request.url.path})

    return Starlette(routes=[Route("/{p:path}", anything, methods=["GET", "POST", "PUT", "DELETE"])])


@pytest.fixture
def env():
    store: dict[str, str] = {}
    clock = {"t": 1_000_000.0}
    auth = C.ConnectorAuth(store.get, lambda k, v: store.pop(k, None) if v is None else store.__setitem__(k, v), lambda: clock["t"])
    auth.set_enabled(True)
    SEEN.clear()
    client = TestClient(C.Connector(stub_api(), auth, lambda: "https://cadence.example.test"), base_url="https://cadence.example.test", follow_redirects=False)
    return client, auth, clock


def sign_in(client, auth):
    cid = client.post("/oauth/register", json={"redirect_uris": [REDIRECT], "client_name": "Claude"}).json()["client_id"]
    code, _ = auth.approval_code()
    form = {"client_id": cid, "redirect_uri": REDIRECT, "response_type": "code", "code_challenge": CHALLENGE, "code_challenge_method": "S256", "state": "s1", "approval": code}
    r = client.post("/oauth/authorize", data=form)
    assert r.status_code == 303 and r.headers["location"].startswith(REDIRECT + "?code=") and "state=s1" in r.headers["location"]
    grant = re.search(r"code=([^&]+)", r.headers["location"]).group(1)
    tok = client.post("/oauth/token", data={"grant_type": "authorization_code", "code": grant, "client_id": cid, "redirect_uri": REDIRECT, "code_verifier": VERIFIER})
    assert tok.status_code == 200
    return cid, tok.json()


def rpc(client, token, method, params=None, mid=1):
    return client.post("/mcp", json={"jsonrpc": "2.0", "id": mid, "method": method, "params": params or {}}, headers={"Authorization": f"Bearer {token}"})


def test_off_by_default_and_metadata_when_on(env):
    client, auth, _ = env
    meta = client.get("/.well-known/oauth-authorization-server").json()
    assert meta["code_challenge_methods_supported"] == ["S256"] and meta["registration_endpoint"] == "https://cadence.example.test/oauth/register"
    assert client.get("/.well-known/oauth-protected-resource").json()["resource"] == "https://cadence.example.test/mcp"
    auth.set_enabled(False)
    assert client.get("/.well-known/oauth-authorization-server").status_code == 404
    assert client.post("/mcp", json={}).status_code == 404


def test_registration_only_for_claude_callbacks(env):
    client, _, _ = env
    assert client.post("/oauth/register", json={"redirect_uris": ["https://evil.example/cb"]}).status_code == 400
    assert client.post("/oauth/register", json={"redirect_uris": [REDIRECT, "http://localhost/cb"]}).status_code == 400
    assert client.post("/oauth/register", json={}).status_code == 400
    assert client.post("/oauth/register", content=b"not json").status_code == 400
    assert client.post("/oauth/register", json={"redirect_uris": [REDIRECT]}).status_code == 201


def test_approval_needs_the_code_and_it_is_single_use_and_throttled(env):
    client, auth, clock = env
    cid = client.post("/oauth/register", json={"redirect_uris": [REDIRECT]}).json()["client_id"]
    base = {"client_id": cid, "redirect_uri": REDIRECT, "response_type": "code", "code_challenge": CHALLENGE, "code_challenge_method": "S256"}
    page = client.get("/oauth/authorize", params=base)
    assert page.status_code == 200 and "Approval code" in page.text
    assert client.get("/oauth/authorize", params={**base, "redirect_uri": "https://evil.example/cb"}).status_code == 400
    assert client.get("/oauth/authorize", params={**base, "code_challenge_method": "plain"}).status_code == 400
    assert client.post("/oauth/authorize", data={**base, "approval": "WRONGCODE1"}).status_code == 403
    code, _ = auth.approval_code()
    ok = client.post("/oauth/authorize", data={**base, "approval": code.lower()})  # typed any way: case and spaces don't matter
    assert ok.status_code == 303
    assert client.post("/oauth/authorize", data={**base, "approval": code}).status_code == 403  # used once
    for _ in range(C.FAIL_FREE + 1):
        client.post("/oauth/authorize", data={**base, "approval": "NOPE"})
    assert client.post("/oauth/authorize", data={**base, "approval": "NOPE"}).status_code == 429
    clock["t"] += C.APPROVAL_TTL_S + 1
    assert auth.approval_code()[0] != code  # a fresh one after it lapses


def test_token_needs_matching_pkce_and_works_once(env):
    client, auth, _ = env
    cid = client.post("/oauth/register", json={"redirect_uris": [REDIRECT]}).json()["client_id"]
    code, _ = auth.approval_code()
    form = {"client_id": cid, "redirect_uri": REDIRECT, "response_type": "code", "code_challenge": CHALLENGE, "code_challenge_method": "S256", "approval": code}
    grant = re.search(r"code=([^&]+)", client.post("/oauth/authorize", data=form).headers["location"]).group(1)
    base = {"grant_type": "authorization_code", "code": grant, "client_id": cid, "redirect_uri": REDIRECT}
    assert client.post("/oauth/token", data={**base, "code_verifier": "w" * 64}).status_code == 400  # wrong verifier burns the code
    assert client.post("/oauth/token", data={**base, "code_verifier": VERIFIER}).status_code == 400


def test_mcp_requires_a_token_and_speaks_the_protocol(env):
    client, auth, _ = env
    r = client.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "ping"})
    assert r.status_code == 401 and "resource_metadata" in r.headers["www-authenticate"]
    assert client.post("/mcp", json={}, headers={"Authorization": "Bearer nope"}).status_code == 401
    assert client.get("/mcp").status_code == 405
    _, tokens = sign_in(client, auth)
    token = tokens["access_token"]
    init = rpc(client, token, "initialize", {"protocolVersion": "2025-06-18"}).json()["result"]
    assert init["protocolVersion"] == "2025-06-18" and init["serverInfo"]["name"] == "cadence" and "read-only" in init["instructions"]
    assert client.post("/mcp", json={"jsonrpc": "2.0", "method": "notifications/initialized"}, headers={"Authorization": f"Bearer {token}"}).status_code == 202
    tools = rpc(client, token, "tools/list").json()["result"]["tools"]
    assert {t["name"] for t in tools} == set(C.TOOLS) and all(t["annotations"]["readOnlyHint"] for t in tools)
    assert rpc(client, token, "nope").json()["error"]["code"] == -32601
    assert rpc(client, token, "tools/call", {"name": "nope"}).json()["error"]["code"] == -32602


def test_tools_only_ever_read_and_validate_their_input(env):
    client, auth, _ = env
    token = sign_in(client, auth)[1]["access_token"]
    call = lambda name, args=None: rpc(client, token, "tools/call", {"name": name, "arguments": args or {}}).json()["result"]  # noqa: E731
    r = call("today")
    assert not r["isError"] and json.loads(r["content"][0]["text"])["path"] == "/api/overview"
    assert call("day", {"day": "2026-11-09"})["isError"] is False
    assert call("day", {"day": "../../etc"})["isError"] and call("day")["isError"]
    assert call("day", {"day": "2000-01-01"})["content"][0]["text"] == "Nothing found for that request."
    assert call("recent_activities", {"limit": 5, "family": "run"})["isError"] is False
    assert call("recent_activities", {"limit": 5000})["isError"] and call("recent_activities", {"limit": True})["isError"]
    assert call("today", {"sneaky": 1})["isError"]
    assert call("review", {"kind": "week"})["isError"] is False and call("review", {"kind": "../x"})["isError"]
    big = call("score")["content"][0]["text"]
    assert "[cut:" in big and len(big) < C.MAX_RESULT_CHARS + 200
    assert SEEN and all(method == "GET" for method, _ in SEEN)
    assert ("GET", "/api/activities?limit=5&family=run") in SEEN


def test_refresh_rotates_and_revoking_cuts_access_at_once(env):
    client, auth, clock = env
    cid, tokens = sign_in(client, auth)
    r = client.post("/oauth/token", data={"grant_type": "refresh_token", "refresh_token": tokens["refresh_token"], "client_id": cid})
    assert r.status_code == 200
    new = r.json()
    assert client.post("/oauth/token", data={"grant_type": "refresh_token", "refresh_token": tokens["refresh_token"], "client_id": cid}).status_code == 400  # rotated
    assert rpc(client, new["access_token"], "ping").status_code == 200
    clock["t"] += C.ACCESS_TTL_S + 1
    assert rpc(client, new["access_token"], "ping").status_code == 401  # access tokens are short-lived
    again = client.post("/oauth/token", data={"grant_type": "refresh_token", "refresh_token": new["refresh_token"], "client_id": cid}).json()
    sid = auth.list()[0]["id"]
    assert auth.revoke(sid) and not auth.revoke(sid)
    assert rpc(client, again["access_token"], "ping").status_code == 401
    assert client.post("/oauth/token", data={"grant_type": "refresh_token", "refresh_token": again["refresh_token"], "client_id": cid}).status_code == 400


def test_only_a_hash_of_the_refresh_token_is_stored(env):
    client, auth, _ = env
    _, tokens = sign_in(client, auth)
    stored = auth._load(C.SESSIONS_KEY)
    assert tokens["refresh_token"] not in stored and tokens["access_token"] not in stored


def test_extra_origins_come_from_the_environment_and_only_those(monkeypatch):
    from cadence_app.config import DEFAULT_ALLOWED_ORIGINS, load_settings

    monkeypatch.setenv("CADENCE_EXTRA_ORIGINS", "http://127.0.0.1:8780/, http://localhost:8780")
    assert load_settings().allowed_origins == DEFAULT_ALLOWED_ORIGINS + ("http://127.0.0.1:8780", "http://localhost:8780")
    monkeypatch.delenv("CADENCE_EXTRA_ORIGINS")
    assert load_settings().allowed_origins == DEFAULT_ALLOWED_ORIGINS
