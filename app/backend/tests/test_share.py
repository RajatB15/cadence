import re
import socket
from datetime import date

import httpx
import pytest
from fastapi.testclient import TestClient

from cadence_app.config import Settings
from cadence_app.main import create_app
from cadence_app.share import COOKIE, PHONE_WRITES, SECURE_COOKIE, TOKEN_KEY, ShareAuth, ShareGate, ShareServer, phone_may_write
from tests.test_api import MUTATE, FixedClock


@pytest.fixture
def web(tmp_path):
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<html><head><title>Cadence</title></head><body></body></html>")
    (dist / "assets" / "app.js").write_text("console.log(1)")
    (tmp_path / "secret.txt").write_text("nope")
    return dist


@pytest.fixture
def api(tmp_path, web):
    secrets = tmp_path / "garmin.env"
    secrets.write_text("GARMIN_API_KEY='not-a-real-key'\n")
    settings = Settings(data_dir=tmp_path / "data", secrets_file=secrets, web_dist=web, share_port=0)
    app = create_app(settings, FixedClock(date(2026, 10, 22)))
    with TestClient(app, base_url="http://127.0.0.1") as client:
        client.post("/api/sync/demo", headers=MUTATE)
        yield app


class Clock:
    def __init__(self):
        self.t = 1_000_000.0

    def __call__(self):
        return self.t


def make_auth(clock=None):
    store: dict[str, str] = {}
    auth = ShareAuth(store.get, lambda k, v: store.pop(k, None) if v is None else store.__setitem__(k, v), clock or Clock())
    auth.store = store
    return auth


def phone(app, web, auth=None, base="http://192.168.1.20:8766"):
    """A client for the share gate; `pair()` below pairs it with a fresh single-use key."""
    auth = auth or make_auth()
    client = TestClient(ShareGate(app, auth, web), base_url=base)
    client.share_auth = auth
    return client


def pair(c, **kw):
    key, _ = c.share_auth.pairing_key()
    return c.get(f"/pair?key={key}", follow_redirects=False, **kw)


def test_unpaired_devices_see_nothing(api, web):
    c = phone(api, web)
    assert c.get("/").status_code == 401
    assert c.get("/api/overview").status_code == 401
    assert c.get("/pair?key=wrong").status_code == 403
    off = TestClient(ShareGate(api, make_auth(), web, lambda: False), base_url="http://192.168.1.20:8766")
    assert off.get("/api/overview").status_code == 503


def test_pairing_sets_cookie_and_allows_reads_only(api, web):
    c = phone(api, web)
    r = pair(c)
    assert r.status_code == 303 and r.headers["location"] == "/"
    cookie = r.headers["set-cookie"].lower()
    assert "httponly" in cookie and "secure" not in cookie and "__host-" not in cookie
    token = c.cookies.get(COOKIE)
    assert token and token not in c.share_auth.store.values() and token not in "".join(c.share_auth.store.values())  # only a hash is stored

    overview = c.get("/api/overview")
    assert overview.status_code == 200 and overview.json()["has_data"]
    assert overview.headers["x-frame-options"] == "DENY"
    assert c.post("/api/sync/demo", headers=MUTATE).status_code == 405
    assert c.get("/api/share").status_code == 404

    page = c.get("/activities/12")
    assert 'name="cadence-mode" content="read-only"' in page.text
    assert c.get("/assets/app.js").text == "console.log(1)"
    assert c.get("/../secret.txt").status_code == 200 and "nope" not in c.get("/../secret.txt").text
    assert "nope" not in c.get("/%2e%2e/secret.txt").text


def test_pairing_key_is_single_use_and_expires(api, web):
    clock = Clock()
    auth = make_auth(clock)
    key, _ = auth.pairing_key()
    a, b = phone(api, web, auth), phone(api, web, auth)
    assert a.get(f"/pair?key={key}", follow_redirects=False).status_code == 303
    assert b.get(f"/pair?key={key}", follow_redirects=False).status_code == 403
    key2, _ = auth.pairing_key()
    assert key2 != key
    clock.t += 11 * 60
    assert b.get(f"/pair?key={key2}", follow_redirects=False).status_code == 403


def test_https_pairing_uses_secure_host_cookie(api, web):
    c = phone(api, web, base="https://cadence.example.ts.net")
    r = pair(c)
    set_cookie = r.headers["set-cookie"].lower()
    assert "__host-cadence_share=" in set_cookie and "secure" in set_cookie and "path=/" in set_cookie
    assert c.get("/api/health").json() == {"ok": True}
    # Through a TLS-terminating proxy (tailscale serve) the scheme arrives in X-Forwarded-Proto.
    p = phone(api, web)
    r = pair(p, headers={"x-forwarded-proto": "https"})
    assert SECURE_COOKIE.lower() in r.headers["set-cookie"].lower()


def test_each_phone_has_its_own_revocable_session(api, web):
    auth = make_auth()
    a, b = phone(api, web, auth), phone(api, web, auth)
    pair(a, headers={"user-agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17) Safari/604"})
    pair(b)
    sessions = auth.list()
    assert len(sessions) == 2 and sessions[0]["label"].startswith("iPhone")
    assert a.get("/api/health").status_code == 200 and b.get("/api/health").status_code == 200
    assert auth.revoke(sessions[0]["id"])
    assert a.get("/api/health").status_code == 401 and b.get("/api/health").status_code == 200
    auth.revoke_all()
    assert b.get("/api/health").status_code == 401


def test_failed_pairing_is_throttled_and_logged_without_keys(api, web, caplog):
    c = phone(api, web)
    with caplog.at_level("WARNING"):
        codes = [c.get("/pair?key=guess-secret").status_code for _ in range(7)]
    assert codes[:5] == [403] * 5 and codes[5] == 403 and codes[6] == 429
    assert "Failed phone pairing attempt" in caplog.text and "guess-secret" not in caplog.text
    real, _ = c.share_auth.pairing_key()
    assert c.get("/pair?key=another-guess").status_code == 429  # a wrong guess while blocked is refused
    assert c.share_auth.pairing_key()[0] == real  # and does not consume the real key
    ok = c.get(f"/pair?key={real}", follow_redirects=False)
    assert ok.status_code == 303  # a valid key always succeeds, even from a blocked client (a stranger cannot lock the owner out)


def test_shared_loopback_bucket_block_is_short_and_global_cap_applies():
    clock = Clock()
    auth = make_auth(clock)
    for _ in range(20):
        auth.try_pair("wrong", "127.0.0.1")
    assert 0 < auth.blocked_for("127.0.0.1") <= 60  # not 15 minutes for everyone behind the proxy
    key, _ = auth.pairing_key()
    token, wait = auth.try_pair(key, "127.0.0.1")
    assert token and wait == 0
    spread = make_auth(Clock())
    for i in range(70):
        spread.try_pair("wrong", f"10.0.0.{i}")
    assert spread.global_blocked()
    assert spread.try_pair("wrong", "10.9.9.9")[1] > 0  # spread-out guessing is throttled as a whole
    key, _ = spread.pairing_key()
    assert spread.try_pair(key, "10.9.9.9")[0]  # but a valid key still pairs


def test_unauthenticated_clients_do_not_learn_the_write_allowlist(api, web):
    c = phone(api, web)
    assert c.post("/api/sync/demo", headers=MUTATE).status_code == 401  # not 405
    assert c.post("/api/journal/behaviours", json={}, headers=MUTATE).status_code == 401
    page = c.get("/")
    assert page.status_code == 401 and "fresh QR" in page.text


def test_legacy_upgrade_only_on_navigation_and_once_per_cookie(api, web):
    auth = make_auth()
    auth.store[TOKEN_KEY] = "legacy-token"
    c = phone(api, web, auth)
    c.cookies.set(COOKIE, "legacy-token", domain="192.168.1.20")
    assert c.get("/assets/app.js").status_code == 200 and len(auth.list()) == 0  # assets do not mint sessions
    assert c.get("/some/page").status_code == 200 and len(auth.list()) == 0
    for _ in range(3):  # parallel tabs/requests still carrying the old cookie
        c.cookies.set(COOKIE, "legacy-token", domain="192.168.1.20")
        assert c.get("/").status_code == 200
    assert len(auth.list()) == 1


def test_old_shared_key_cookie_is_upgraded_in_place(api, web):
    auth = make_auth()
    auth.store[TOKEN_KEY] = "legacy-token"
    c = phone(api, web, auth)
    c.cookies.set(COOKIE, "legacy-token", domain="192.168.1.20")
    assert c.get("/api/health").status_code == 200
    r = c.get("/")
    assert r.status_code == 200 and "set-cookie" in r.headers and len(auth.list()) == 1
    assert c.cookies.get(COOKIE) != "legacy-token"
    assert c.get("/api/health").status_code == 200
    auth.revoke_all()
    c.cookies.set(COOKIE, "legacy-token", domain="192.168.1.20")
    assert c.get("/api/health").status_code == 401


def test_share_server_listens_and_persists_token(tmp_path, api, web):
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    server = ShareServer(api, api.state.share.factory, web, port, host="127.0.0.1")
    server.start()
    try:
        assert server.running
        status = server.status()
        assert status["running"] and status["qr"] and status["insecure_lan"] is not status["secure"]
        key = status["pair_url"].rsplit("key=", 1)[1]
        with httpx.Client(base_url=f"http://127.0.0.1:{port}") as http:
            assert http.get("/api/health").status_code == 401
            http.get(f"/pair?key={key}")
            assert http.get("/api/health").json() == {"ok": True}
            assert len(server.status()["sessions"]) == 1
            server.reset()
            assert http.get("/api/health").status_code == 401
    finally:
        server.stop()
    assert not server.running


def test_share_endpoints_on_loopback(tmp_path):
    secrets = tmp_path / "garmin.env"
    secrets.write_text("")
    app = create_app(Settings(data_dir=tmp_path / "data", secrets_file=secrets, web_dist=tmp_path / "missing"))
    with TestClient(app, base_url="http://127.0.0.1") as client:
        assert client.get("/api/share").json()["running"] is False
        r = client.post("/api/share/start", headers=MUTATE)
        assert r.status_code == 409 and "npm run build" in r.json()["detail"]
        assert client.post("/api/share/start").status_code == 403


def test_paired_phone_can_write_the_journal_but_nothing_else(api, web):
    c = phone(api, web)
    pair(c)
    assert c.get("/api/journal").status_code == 200
    r = c.put("/api/journal/2026-10-21", json={"answers": {"alcohol": 2}}, headers=MUTATE)
    assert r.status_code == 200 and r.json()["answers"]["alcohol"] == 2
    assert c.post("/api/sync/demo", headers=MUTATE).status_code == 405
    assert c.put("/api/settings/goal", json={}, headers=MUTATE).status_code == 405


def test_paired_phone_can_name_a_strength_class(api, web):
    c = phone(api, web)
    pair(c)
    text = "Get Stronger\nBarbell Front Squats\nGlute Bridges\nCore\nBeast Hold drag"
    assert c.post("/api/strength/parse", json={"text": text}, headers=MUTATE).json()["summary"]["heavy_lower"]
    aid = c.get("/api/activities?family=strength&limit=1").json()["items"][0]["id"]
    r = c.put(f"/api/strength/{aid}", json={"text": text}, headers=MUTATE)
    assert r.status_code == 200 and len(r.json()["blocks"]) == 2


def test_phone_write_allowlist_is_anchored():
    assert phone_may_write("PUT", "/api/journal/2026-10-21")
    assert phone_may_write("POST", "/api/food/meals/3/log")
    assert phone_may_write("POST", "/api/food/log")
    assert phone_may_write("POST", "/api/food/entries/bulk")
    assert phone_may_write("POST", "/api/food/entries/7/restore")
    assert phone_may_write("POST", "/api/food/dishes/12/names")
    assert phone_may_write("PATCH", "/api/food/dishes/12/names/3")
    assert phone_may_write("DELETE", "/api/food/dishes/12/names/3")
    assert not phone_may_write("DELETE", "/api/food/dishes/12")
    assert not phone_may_write("POST", "/api/food/dishes/12/names/3")
    assert not phone_may_write("POST", "/api/food/dishes/12/names/")
    assert not phone_may_write("POST", "/api/food/log/x")
    assert not phone_may_write("PUT", "/api/food/log")
    assert not phone_may_write("POST", "/api/food/entries/7/restore/x")
    assert not phone_may_write("POST", "/api/food/barcode/12345678/lookup")  # no online lookup exists
    assert not phone_may_write("POST", "/api/planner/3/garmin")
    assert not phone_may_write("DELETE", "/api/planner/3/garmin")
    assert not phone_may_write("POST", "/api/reading/feed/refresh")
    assert not phone_may_write("PUT", "/api/settings/reading-feed")
    assert not phone_may_write("POST", "/api/garmin/rebuild")
    assert not phone_may_write("POST", "/api/push/subscribe/extra")
    assert not phone_may_write("POST", "/api/journalx/behaviours")
    assert not phone_may_write("DELETE", "/api/push/test")  # method matters
    assert not phone_may_write("POST", "/api/settings/plan")
    assert phone_may_write("PUT", "/api/settings/calories")
    assert not phone_may_write("POST", "/api/settings/calories")
    assert not phone_may_write("PUT", "/api/settings/calories/extra")
    assert phone_may_write("POST", "/api/activities/12/fetch")
    assert not phone_may_write("POST", "/api/activities/1/fetch/x")
    assert not phone_may_write("POST", "/api/activities/abc/fetch")
    assert not phone_may_write("GET", "/api/activities/1/fetch")


def test_every_write_route_is_either_allowlisted_or_blocked_from_the_phone(api, web):
    """Fails when someone adds a mutating route that a paired phone can reach without it being on the allowlist."""
    from fastapi.routing import APIRoute

    c = phone(api, web)
    pair(c)
    write_routes = [(m, r.path) for r in api.routes if isinstance(r, APIRoute) for m in r.methods if m not in ("GET", "HEAD", "OPTIONS")]
    assert len(write_routes) > 40
    for method, template in write_routes:
        path = re.sub(r"\{[^}]+\}", "1", template)
        allowed = phone_may_write(method, path)
        if not allowed:  # blocked requests never reach a handler, so this is safe to send
            response = c.request(method, path, headers=MUTATE)
            assert response.status_code in (404, 405), f"{method} {template} reachable from a paired phone but not on PHONE_WRITES"
            assert response.status_code == 405 or template.startswith("/api/share"), (method, template)
    allowed_routes = {(m, t) for m, t in write_routes if phone_may_write(m, re.sub(r"\{[^}]+\}", "1", t))}
    never = ["/api/planner/{plan_id}/garmin", "/api/reading/feed/refresh", "/api/garmin/rebuild", "/api/garmin/stop", "/api/garmin-connect", "/api/garmin-connect/login",
             "/api/settings/goal", "/api/settings/reading-feed", "/api/settings/training-mode", "/api/settings/weight-goal", "/api/goals", "/api/events", "/api/sync/demo",
             "/api/sources/demo/data", "/api/credentials/reminders/dismiss", "/api/share/reset", "/api/days/{day}/fetch"]
    assert not [(m, t) for m, t in allowed_routes if t in never]
    # Every allowlist entry must still match a real route, so renames don't leave dead (or accidentally broad) rules.
    for method, rx in PHONE_WRITES:
        assert any(m == method and rx.fullmatch(re.sub(r"\{[^}]+\}", "1", t)) for m, t in write_routes), (method, rx.pattern)


def test_public_url_is_the_pairing_address(api, web):
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    server = ShareServer(api, api.state.share.factory, web, port, host="127.0.0.1", public_url="https://cadence.example.test")
    server.start()
    try:
        status = server.status()
        assert status["secure"] and not status["insecure_lan"]
        assert status["urls"][0] == "https://cadence.example.test"
        assert status["pair_url"].startswith("https://cadence.example.test/pair?key=")
    finally:
        server.stop(remember=False)
