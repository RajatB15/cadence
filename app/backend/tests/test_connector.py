import base64
from datetime import date
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
SEEN_BODIES: list[tuple[str, str, str]] = []


def stub_api():
    async def anything(request):
        SEEN.append((request.method, request.url.path + ("?" + request.url.query if request.url.query else "")))
        if request.url.path == "/api/days/2000-01-01":
            return JSONResponse({"detail": "none"}, status_code=404)
        if request.method != "GET":
            SEEN_BODIES.append((request.method, request.url.path, (await request.body()).decode()))
            if request.url.path == "/api/food/log":
                return JSONResponse({"detail": "Pick a dish, or give a name and calories"}, status_code=400) if b"BAD" in await request.body() else JSONResponse({"entries": [{"id": 7}]})
        if request.url.path == "/api/score":
            return JSONResponse({"blob": "x" * (C.MAX_RESULT_CHARS + 500)})
        return JSONResponse({"ok": True, "path": request.url.path})

    return Starlette(routes=[Route("/{p:path}", anything, methods=["GET", "POST", "PUT", "PATCH", "DELETE"])])


@pytest.fixture
def env():
    store: dict[str, str] = {}
    clock = {"t": 1_000_000.0}
    auth = C.ConnectorAuth(store.get, lambda k, v: store.pop(k, None) if v is None else store.__setitem__(k, v), lambda: clock["t"])
    auth.set_enabled(True)
    SEEN.clear()
    SEEN_BODIES.clear()
    client = TestClient(C.Connector(stub_api(), auth, lambda: "https://cadence.example.test", lambda: date(2026, 11, 10)), base_url="https://cadence.example.test", follow_redirects=False)
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
    assert {t["name"] for t in tools} == {n for n, t in C.TOOLS.items() if not t.get("write")} and all(t["annotations"]["readOnlyHint"] for t in tools)
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
    assert SEEN and all(method == "GET" for method, _ in SEEN) and not SEEN_BODIES  # reading never writes
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


def test_writes_are_off_until_switched_on_and_then_limited_to_logging(env):
    client, auth, _ = env
    token = sign_in(client, auth)[1]["access_token"]
    call = lambda name, args=None: rpc(client, token, "tools/call", {"name": name, "arguments": args or {}}).json()  # noqa: E731
    names = lambda: {t["name"] for t in rpc(client, token, "tools/list").json()["result"]["tools"]}  # noqa: E731
    assert "log_food" not in names() and "find_food" in names()
    r = call("log_weight", {"weight_kg": 70})["result"]
    assert r["isError"] and "isn't switched on" in r["content"][0]["text"] and not SEEN_BODIES
    auth.set_writes(True)
    listed = {t["name"]: t for t in rpc(client, token, "tools/list").json()["result"]["tools"]}
    assert {"log_food", "log_saved_meal", "remove_food_entry", "log_weight", "log_check_in"} <= set(listed)
    assert listed["log_food"]["annotations"]["readOnlyHint"] is False and listed["remove_food_entry"]["annotations"]["destructiveHint"] is True
    assert listed["log_weight"]["annotations"]["destructiveHint"] is False
    # Nothing outside the logging tools exists, whatever it is called.
    assert call("delete_everything")["error"]["code"] == -32602
    # Day defaults to today, the body is only what was asked.
    assert call("log_weight", {"weight_kg": 70.4})["result"]["isError"] is False
    assert SEEN_BODIES[-1] == ("POST", "/api/weight/entries", json.dumps({"weight_kg": 70.4, "day": "2026-11-10"}, separators=(",", ":")))
    assert call("log_weight", {"weight_kg": 5})["result"]["isError"] and call("log_weight", {"weight_kg": True})["result"]["isError"]
    assert call("log_weight", {"weight_kg": 70, "day": "yesterday"})["result"]["isError"]
    ok = call("log_food", {"meal": "lunch", "items": [{"dish_id": 3, "servings": 1}, {"name": "Paneer fry", "kcal": 320, "protein_g": 22}]})["result"]
    assert not ok["isError"] and json.loads(SEEN_BODIES[-1][2])["meal"] == "lunch" and json.loads(SEEN_BODIES[-1][2])["day"] == "2026-11-10"
    for bad in ([], [{"dish_id": 3, "name": "x"}], [{"kcal": 5}], [{"name": "x", "kcal": 5, "save_dish": True}], [{"dish_id": "3"}], "eggs", [{"dish_id": 1}] * 13):
        assert call("log_food", {"meal": "lunch", "items": bad})["result"]["isError"], bad
    assert call("log_food", {"meal": "brunch", "items": [{"dish_id": 1}]})["result"]["isError"]
    app_said_no = call("log_food", {"meal": "lunch", "items": [{"name": "BAD", "kcal": 5}]})["result"]
    assert app_said_no["isError"] and "Pick a dish" in app_said_no["content"][0]["text"]  # the app's own reason is passed on
    assert call("remove_food_entry", {"entry_id": 7})["result"]["isError"] is False and SEEN_BODIES[-1][0] == "DELETE"
    assert call("log_saved_meal", {"meal_id": 2, "meal": "lunch", "scale": 1.5})["result"]["isError"] is False
    assert call("log_check_in")["result"]["isError"]  # nothing to save
    assert call("log_check_in", {"feel": 4, "note": "slept well"})["result"]["isError"] is False
    assert SEEN_BODIES[-1][:2] == ("PUT", "/api/wellbeing/2026-11-10") and json.loads(SEEN_BODIES[-1][2]) == {"feel": 4, "note": "slept well"}
    assert call("log_check_in", {"feel": 9})["result"]["isError"]
    assert {m for m, _, _ in SEEN_BODIES} <= {"POST", "PUT", "DELETE"}
    audit = auth.recent()
    assert audit[0]["tool"] == "log_check_in" and all("kcal" not in a["summary"] and "Paneer" not in a["summary"] for a in audit)  # what changed, never the content


def test_turning_the_connector_off_turns_writes_off(env):
    _, auth, _ = env
    auth.set_writes(True)
    auth.set_writes(True, "plan")
    assert auth.writes_enabled() and auth.writes_enabled("plan")
    auth.set_enabled(False)
    auth.set_enabled(True)
    assert not auth.writes_enabled() and not auth.writes_enabled("plan")


PLAN_TOOLS = {"add_planned_session", "remove_planned_session", "set_race_goal", "clear_race_goal", "create_goal", "update_goal", "add_time_off", "remove_time_off"}


def test_plan_and_goal_tools_have_their_own_switch(env):
    client, auth, _ = env
    token = sign_in(client, auth)[1]["access_token"]
    call = lambda name, args=None: rpc(client, token, "tools/call", {"name": name, "arguments": args or {}}).json()["result"]  # noqa: E731
    names = lambda: {t["name"] for t in rpc(client, token, "tools/list").json()["result"]["tools"]}  # noqa: E731
    auth.set_writes(True)  # logging on does not open the plan
    assert not (PLAN_TOOLS & names()) and "log_food" in names() and "plan_options" in names()
    r = call("set_race_goal", {"distance": "marathon", "date": "2027-03-14"})
    assert r["isError"] and "change plan and goals" in r["content"][0]["text"] and not SEEN_BODIES
    auth.set_writes(True, "plan")
    assert PLAN_TOOLS <= names()
    listed = {t["name"]: t for t in rpc(client, token, "tools/list").json()["result"]["tools"]}
    assert listed["remove_planned_session"]["annotations"]["destructiveHint"] and listed["clear_race_goal"]["annotations"]["destructiveHint"]
    assert not listed["set_race_goal"]["annotations"]["destructiveHint"] and not listed["set_race_goal"]["annotations"]["readOnlyHint"]
    assert not call("set_race_goal", {"distance": "marathon", "date": "2027-03-14", "target_s": 13500})["isError"]
    assert SEEN_BODIES[-1] == ("PUT", "/api/settings/goal", json.dumps({"distance": "marathon", "date": "2027-03-14", "target_s": 13500}, separators=(",", ":")))
    for bad in ({"distance": "ultra", "date": "2027-03-14"}, {"distance": "marathon"}, {"distance": "marathon", "date": "soon"}, {"distance": "marathon", "date": "2027-03-14", "target_s": 5}):
        assert call("set_race_goal", bad)["isError"], bad
    assert not call("clear_race_goal")["isError"] and SEEN_BODIES[-1] == ("PUT", "/api/settings/goal", "{}")
    assert not call("create_goal", {"kind": "race", "sport": "run", "date": "2027-03-14", "distance_m": 42195, "label": "Marathon"})["isError"]
    assert call("create_goal", {"kind": "triathlon"})["isError"] and call("create_goal", {"kind": "race", "distance_m": -4})["isError"]
    assert not call("update_goal", {"goal_id": 3, "status": "achieved"})["isError"] and SEEN_BODIES[-1][:2] == ("PATCH", "/api/goals/3")
    assert call("update_goal", {"goal_id": 3})["isError"] and call("update_goal", {"goal_id": 3, "status": "deleted"})["isError"]
    assert not call("add_planned_session", {"day": "2026-11-12", "sport": "run", "option_key": "easy_45", "start_hour": 6})["isError"]
    assert call("add_planned_session", {"day": "2026-11-12", "sport": "run", "option_key": "../x"})["isError"]
    assert not call("remove_planned_session", {"plan_id": 9})["isError"] and SEEN_BODIES[-1][:2] == ("DELETE", "/api/planner/9")
    assert not call("add_time_off", {"kind": "travel", "start": "2026-12-01", "end": "2026-12-05", "activity": "light"})["isError"]
    assert call("add_time_off", {"kind": "vacation", "start": "2026-12-01", "severity": 7})["isError"]
    assert not call("remove_time_off", {"entry_id": 2})["isError"]
    opts = call("plan_options", {"day": "2026-11-12", "sport": "run", "custom": True, "distance_m": 8000, "effort": "easy"})
    assert not opts["isError"] and ("GET", "/api/planner/options?day=2026-11-12&sport=run&distance_m=8000&effort=easy&custom=true") in SEEN
    assert call("plan_options", {"day": "2026-11-12", "sport": "run", "custom": "yes"})["isError"]
    # Nothing outside this list is reachable: no plan settings, credentials, sharing or Garmin.
    for hidden in ("set_plan_settings", "garmin_push", "set_credentials", "share_reset"):
        assert hidden not in TOOLS_ALL()


def TOOLS_ALL():
    return set(C.TOOLS)
