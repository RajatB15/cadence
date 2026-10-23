import socket
from datetime import date

import httpx
import pytest
from fastapi.testclient import TestClient

from cadence_app.config import Settings
from cadence_app.main import create_app
from cadence_app.share import COOKIE, ShareGate, ShareServer
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


def phone(app, web, token="tok"):
    return TestClient(ShareGate(app, lambda: token, web), base_url="http://192.168.1.20:8766")


def test_unpaired_devices_see_nothing(api, web):
    c = phone(api, web)
    assert c.get("/").status_code == 401
    assert c.get("/api/overview").status_code == 401
    assert c.get("/pair?key=wrong").status_code == 403
    assert phone(api, web, token=None).get("/api/overview").status_code == 503


def test_pairing_sets_cookie_and_allows_reads_only(api, web):
    c = phone(api, web)
    r = c.get("/pair?key=tok", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/"
    assert "httponly" in r.headers["set-cookie"].lower()
    assert c.cookies.get(COOKIE) == "tok"

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


def test_rotating_the_key_unpairs_phones(api, web):
    token = {"v": "old"}
    c = TestClient(ShareGate(api, lambda: token["v"], web), base_url="http://192.168.1.20:8766")
    c.get("/pair?key=old")
    assert c.get("/api/health").status_code == 200
    token["v"] = "new"
    assert c.get("/api/health").status_code == 401


def test_share_server_listens_and_persists_token(tmp_path, api, web):
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    server = ShareServer(api, api.state.share.factory, web, port, host="127.0.0.1")
    server.start()
    try:
        assert server.running
        token = server.token()
        with httpx.Client(base_url=f"http://127.0.0.1:{port}") as http:
            assert http.get("/api/health").status_code == 401
            http.get(f"/pair?key={token}")
            assert http.get("/api/health").json() == {"ok": True}
        status = server.status()
        assert status["running"] and status["qr"] and status["pair_url"].endswith(token)
    finally:
        server.stop()
    assert not server.running and server.token() == token
    server.reset()
    assert server.token() != token


def test_share_endpoints_on_loopback(tmp_path):
    secrets = tmp_path / "garmin.env"
    secrets.write_text("")
    app = create_app(Settings(data_dir=tmp_path / "data", secrets_file=secrets, web_dist=tmp_path / "missing"))
    with TestClient(app, base_url="http://127.0.0.1") as client:
        assert client.get("/api/share").json()["running"] is False
        r = client.post("/api/share/start", headers=MUTATE)
        assert r.status_code == 409 and "npm run build" in r.json()["detail"]
        assert client.post("/api/share/start").status_code == 403
