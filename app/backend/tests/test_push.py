import json
import stat
from datetime import date, datetime, timedelta

import http_ece
import httpx
import pytest
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
from fastapi.testclient import TestClient

from cadence_app import push
from cadence_app.config import Settings
from cadence_app.main import create_app
from cadence_app.share import COOKIE, ShareGate
from tests.test_api import MUTATE, FixedClock

APPLE = "https://web.push.apple.com/QGuQyavXutnMH"


def receiver():
    key = ec.generate_private_key(ec.SECP256R1())
    auth = b"0123456789abcdef"
    pub = key.public_key().public_bytes(Encoding.X962, PublicFormat.UncompressedPoint)
    return key, auth, {"p256dh": push.b64url(pub), "auth": push.b64url(auth)}


class FakePost:
    def __init__(self, status=201):
        self.status, self.calls = status, []

    def __call__(self, url, content, headers, timeout):
        self.calls.append((url, content, headers))
        return httpx.Response(self.status)


@pytest.fixture
def app_env(tmp_path):
    secrets = tmp_path / "garmin.env"
    expires = date(2026, 10, 22) + timedelta(days=5)
    secrets.write_text(f"GARMIN_API_KEY='not-a-real-key'\nGARMIN_API_KEY_EXPIRES_ON={expires}\n")
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("<html><head></head><body>cadence</body></html>")
    app = create_app(Settings(data_dir=tmp_path / "data", secrets_file=secrets, web_dist=dist), FixedClock(date(2026, 10, 22)))
    with TestClient(app, base_url="http://127.0.0.1") as client:
        client.post("/api/sync/demo", headers=MUTATE)
        yield app, client, tmp_path


def test_vapid_key_is_private_and_stable(app_env):
    app, client, tmp_path = app_env
    key_file = tmp_path / "data" / "push-vapid.pem"
    assert stat.S_IMODE(key_file.stat().st_mode) == 0o600
    first = client.get("/api/push").json()["public_key"]
    again = push.PushSender(app.state.share.factory, key_file, "mailto:x@example.com", datetime.now).public_key
    assert first == again and len(push.b64url_decode(first)) == 65


def test_subscribe_validates_push_service(app_env):
    _, client, _ = app_env
    _, _, keys = receiver()
    bad = client.post("/api/push/subscribe", headers=MUTATE, json={"endpoint": "https://evil.example/x", "keys": keys})
    assert bad.status_code == 400
    ok = client.post("/api/push/subscribe", headers=MUTATE, json={"endpoint": APPLE, "keys": keys, "label": "iPhone"})
    assert [d["label"] for d in ok.json()["devices"]] == ["iPhone"]
    assert client.post("/api/push/unsubscribe", headers=MUTATE, json={"endpoint": APPLE}).json()["devices"] == []


def test_broadcast_encrypts_for_the_device_and_prunes_revoked(app_env):
    app, client, tmp_path = app_env
    key, auth, keys = receiver()
    client.post("/api/push/subscribe", headers=MUTATE, json={"endpoint": APPLE, "keys": keys})
    fake = FakePost(201)
    sender = push.PushSender(app.state.share.factory, tmp_path / "data" / "push-vapid.pem", "mailto:x@example.com", datetime.now, fake)
    assert sender.broadcast("Readiness 70", "Go hard", "/coach") == 1
    url, body, headers = fake.calls[0]
    assert url == APPLE and headers["Authorization"].startswith("vapid t=") and headers["Content-Encoding"] == "aes128gcm"
    payload = json.loads(http_ece.decrypt(body, private_key=key, auth_secret=auth, version="aes128gcm"))
    assert payload == {"title": "Readiness 70", "body": "Go hard", "url": "/coach", "tag": None}

    gone = push.PushSender(app.state.share.factory, tmp_path / "data" / "push-vapid.pem", "mailto:x@example.com", datetime.now, FakePost(410))
    assert gone.broadcast("x", "y") == 0
    assert client.get("/api/push").json()["devices"] == []


def test_notifier_sends_each_notification_once(app_env):
    app, client, _ = app_env
    _, _, keys = receiver()
    client.post("/api/push/subscribe", headers=MUTATE, json={"endpoint": APPLE, "keys": keys})
    notifier = app.state.notifier
    notifier.sender.post = FakePost(201)
    morning = datetime(2026, 10, 21, 7, 30)
    kinds = {n["kind"] for n in notifier.due(morning)}
    assert {"morning", "reminders"} <= kinds
    sent = notifier.tick(morning, morning)
    assert any(k.startswith("morning:2026-10-21") for k in sent)
    assert notifier.tick(morning, morning) == []
    # The nudge follows tonight's bedtime (exact timing is covered by test_bedtime_push_moves_with_tonight).
    assert "bedtime" not in {n["kind"] for n in notifier.due(datetime(2026, 10, 21, 18, 30))}
    bedtime = next(n for n in notifier.due(datetime(2026, 10, 21, 23, 50)) if n["kind"] == "bedtime")
    assert bedtime["title"].startswith("In bed by")

    client.put("/api/push/prefs", headers=MUTATE, json={"bedtime": False})
    assert "bedtime" not in {n["kind"] for n in notifier.due(datetime(2026, 10, 22, 22, 40))}
    assert client.get("/api/push").json()["recent"][0]["delivered"] == 1


def test_scheduler_syncs_on_interval_and_faster_in_the_morning(app_env):
    app, _, _ = app_env
    started = []
    s = push.Scheduler(app.state.share.factory, app.state.notifier, started.append, lambda: False, lambda: True, datetime.now, 3)
    s.last_sync = lambda: datetime(2026, 10, 22, 12, 0)
    assert not s.sync_due(datetime(2026, 10, 22, 14, 0), datetime(2026, 10, 22, 12, 40))
    assert s.sync_due(datetime(2026, 10, 22, 14, 0), datetime(2026, 10, 22, 13, 1))  # hourly while awake
    assert not s.sync_due(datetime(2026, 10, 23, 2, 0), datetime(2026, 10, 22, 14, 0))  # 3-hourly overnight
    s.last_sync = lambda: datetime(2026, 10, 22, 6, 0)
    assert s.sync_due(datetime(2026, 10, 22, 7, 0), datetime(2026, 10, 22, 6, 50))
    s.run_once(datetime(2026, 10, 22, 7, 0), datetime(2026, 10, 22, 6, 50))
    assert started == ["quick"]


def test_paired_phone_can_manage_notifications_only(app_env):
    app, _, tmp_path = app_env
    _, _, keys = receiver()
    phone = TestClient(ShareGate(app, lambda: "tok", tmp_path / "dist"), base_url="http://192.168.1.20:8766")
    phone.cookies.set(COOKIE, "tok")
    r = phone.post("/api/push/subscribe", headers={**MUTATE, "Origin": "http://192.168.1.20:8766"},
                   json={"endpoint": APPLE, "keys": keys, "label": "iPhone"})
    assert r.status_code == 200
    assert phone.post("/api/garmin/sync", headers=MUTATE, json={"mode": "quick"}).status_code != 405
    assert phone.post("/api/sync/demo", headers=MUTATE).status_code == 405
    assert phone.put("/api/settings/weight-goal", headers=MUTATE, json={"goal_kg": 70}).status_code == 405


def test_backend_serves_the_built_site(app_env):
    _, client, _ = app_env
    assert "cadence" in client.get("/coach").text
    assert client.get("/api/does-not-exist").status_code == 404


def test_weekly_and_monthly_reviews_are_pushed_once(app_env):
    app, client, _ = app_env
    _, _, keys = receiver()
    client.post("/api/push/subscribe", headers=MUTATE, json={"endpoint": APPLE, "keys": keys})
    notifier = app.state.notifier
    notifier.sender.post = FakePost(201)
    sunday = datetime(2026, 10, 18, 19, 5)
    assert "review" not in {n["kind"] for n in notifier.due(datetime(2026, 10, 18, 18, 0))}
    review = next(n for n in notifier.due(sunday) if n["kind"] == "review")
    assert review["title"].startswith("Week in review: ") and "Next:" in review["body"] and "start=2026-10-12" in review["url"]
    assert any(k == "review-week:2026-10-12" for k in notifier.tick(sunday, sunday))
    assert "review" not in {n["kind"] for n in notifier.due(sunday)}
    first = datetime(2026, 10, 1, 9, 30)
    assert next(n for n in notifier.due(first) if n["kind"] == "review")["title"].startswith("September in review")
