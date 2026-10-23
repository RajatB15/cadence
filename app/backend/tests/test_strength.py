import random
from datetime import timedelta

from cadence_app.analytics import exercises as X
from cadence_app.analytics import notes
from cadence_app.analytics.insights import coach
from tests.test_api import MUTATE, env  # noqa: F401  (fixture)
from tests.test_notes import D0, EASY, HARD, act, ctx

CLASS = """11:35
adidas strength+
Get Stronger
Embrace the weights, honor your rest.
Barbell Front Squats
Glute Bridges
Anaerobic Endurance
High-intensity interval training
Unleash the storm, make every second transform!
1.5 Goblet squat
Sprawlees
Wtd Reverse Nordics
Core
Beast Hold drag
Bodyweight crunches
BOOK NOW
WHAT TO BRING
Workout Shoes, Mobile Phone"""


def test_parses_a_class_screenshot_into_blocks():
    blocks = X.parse(CLASS)
    assert [(b["name"], b["kind"]) for b in blocks] == [
        ("Get Stronger", "strength"), ("High-intensity interval training", "conditioning"), ("Core", "core")]
    assert [e["pattern"] for e in blocks[1]["exercises"]] == ["squat", "plyometric", "squat"]
    assert blocks[0]["exercises"][0]["loaded"] and not blocks[0]["exercises"][1]["loaded"]
    s = X.summary(blocks)
    assert s["heavy_lower"] and s["patterns"] == {"squat": 3, "hinge": 1, "plyometric": 1, "core": 2} and not s["unknown"]


def test_hash_titles_and_unknown_exercises():
    blocks = X.parse("# Part A\nTurkish get-up\nKettlebell swings\nMystery move\nPush-ups\n#Finisher\nBurpees")
    assert [b["name"] for b in blocks] == ["Part A", "Finisher"]
    assert [e["name"] for e in blocks[0]["exercises"]] == ["Turkish get-up", "Kettlebell swings", "Mystery move", "Push-ups"]
    assert X.summary(blocks)["unknown"] == ["Turkish get-up", "Mystery move"]
    assert X.parse("Nothing here\nat all") == []


def test_segments_follow_the_heart_rate_shape():
    rng = random.Random(1)
    t, hr, s = [], [], 0
    for dur, base, amp in [(600, 105, 3), (1200, 135, 12), (900, 160, 6), (600, 120, 4), (300, 100, 2)]:
        for x in range(0, dur, 2):
            t.append(s + x)
            hr.append(base + amp * (1 if (x // 60) % 2 else -1) + rng.gauss(0, 2))
        s += dur
    r = X.segment(t, hr, X.parse(CLASS), {"floors": [100, 120, 140, 155, 170]})
    bounds = [(g["start_s"], g["end_s"]) for g in r["segments"]]
    expected = [(0, 600), (600, 1800), (1800, 2700), (2700, 3300), (3300, 3600)]
    assert all(abs(a[0] - b[0]) <= 30 and abs(a[1] - b[1]) <= 30 for a, b in zip(bounds, expected))
    assert r["segments"][2]["hard_pct"] >= 40 and r["fit"] > 0.3
    assert X.segment(t[:100], hr[:100], X.parse(CLASS)) is None  # too short for the structure


def test_heavy_legs_before_a_key_run_is_flagged():
    gym = act(500, D0 + timedelta(days=40), (3000, 600, 0, 0, 0), family="strength", load=60, distance_m=None)
    run = act(501, D0 + timedelta(days=41), HARD)
    easy = [act(i, D0 + timedelta(days=i * 3), EASY) for i in range(13)]
    labels = {500: {"blocks": X.parse(CLASS), "summary": X.summary(X.parse(CLASS))}}
    c = ctx(easy + [gym, run], {}, days=45, labels=labels)
    assert any(f["id"] == "heavy_legs" for f in coach(c))
    assert any(n["id"] == "heavy_legs" for n in notes.session(c, 501)["notes"])
    assert c["strength_content"]["labelled_28d"] == 1 and c["strength_content"]["patterns_28d"]["squat"] == 1


def test_label_survives_an_offline_rebuild(env):  # noqa: F811
    client, _ = env
    client.post("/api/sync/demo", headers=MUTATE)
    items = client.get("/api/activities?family=strength&limit=1").json()["items"]
    aid = items[0]["id"]
    assert client.post("/api/strength/parse", json={"text": CLASS}, headers=MUTATE).json()["summary"]["heavy_lower"]
    saved = client.put(f"/api/strength/{aid}", json={"text": CLASS, "template": "adidas strength+"}, headers=MUTATE)
    assert saved.status_code == 200 and len(saved.json()["blocks"]) == 3
    detail = client.get(f"/api/activities/{aid}").json()["strength"]
    assert detail["label"]["summary"]["exercises"] == 7 and detail["templates"][0]["name"] == "adidas strength+"
    run = client.get("/api/activities?family=run&limit=1").json()["items"][0]["id"]
    assert client.put(f"/api/strength/{run}", json={"text": CLASS}, headers=MUTATE).status_code == 400
    assert client.put(f"/api/strength/{aid}", json={"text": "nothing useful"}, headers=MUTATE).status_code == 400
    # Recreate the activity rows (new ids, same Garmin ids): the label must follow the session.
    client.delete("/api/sources/demo/data", headers=MUTATE)
    client.post("/api/sync/demo", headers=MUTATE)
    again = client.get("/api/activities?family=strength&limit=1").json()["items"][0]["id"]
    assert client.get(f"/api/activities/{again}").json()["strength"]["label"] is not None
