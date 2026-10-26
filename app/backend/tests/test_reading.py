import json
from datetime import date, timedelta

from cadence_app.analytics import reading as R
from cadence_app import reading as store
from cadence_app.config import Settings
from cadence_app.main import create_app
from fastapi.testclient import TestClient
from tests.test_api import MUTATE, FixedClock

SRC = {"name": "Synthetic source", "url": "https://example.org/x", "licence": "Link only"}


def card(i, topic="nutrition", **kw):
    return {"id": f"c{i}", "topic": topic, "title": f"Card {i}", "summary": "A summary.", "takeaways": ["a"],
            "evidence": "review", "source": SRC, **kw}


def cards(n=12):
    return [card(i, list(R.TOPICS)[i % len(R.TOPICS)]) for i in range(n)]


D = date(2026, 10, 22)


def test_pick_is_deterministic_and_rotates_topics():
    cs = [store._clean(c) for c in cards()]
    a, b = R.pick(cs, {}, D), R.pick(cs, {}, D)
    assert a == b and a["card"]["topic"] in R.TOPICS
    topics = {R.pick(cs, {}, D + timedelta(days=i))["card"]["topic"] for i in range(6)}
    assert len(topics) >= 4  # a week is varied


def test_signals_steer_to_recovery_and_fuelling():
    cs = [store._clean(c) for c in cards(24)]
    rest = R.pick(cs, {}, D, {"kind": "rest", "readiness": 80})
    assert rest["card"]["topic"] in ("recovery", "wellbeing") and "rest" in rest["why"]
    low = R.pick(cs, {}, D, {"kind": "key", "readiness": 45})
    assert low["card"]["topic"] in ("recovery", "wellbeing") and "low" in low["why"]
    hard = R.pick(cs, {}, D, {"kind": "long", "readiness": 85})
    assert hard["card"]["topic"] in ("nutrition", "pushing-hard")


def test_read_and_skipped_are_not_repeated_until_exhausted():
    cs = [store._clean(c) for c in cards(3)]
    status = {"c0": "read", "c1": "skipped"}
    assert R.pick(cs, status, D)["card"]["id"] == "c2"
    status["c2"] = "read"
    again = R.pick(cs, status, D)
    assert again["repeat"] and again["card"]["id"] in ("c0", "c2")  # skipped stays out
    assert R.pick([], {}, D) is None


def test_same_topic_not_two_days_running():
    cs = [store._clean(c) for c in cards(12)]
    first = R.pick(cs, {}, D)["card"]["topic"]
    assert R.pick(cs, {}, D + timedelta(days=1), yesterday_topic=first)["card"]["topic"] != first


def test_invalid_cards_are_skipped(tmp_path):
    folder = tmp_path / "cards"
    folder.mkdir()
    bad = [card(1, topic="astrology"), card(2, source={"name": "x", "url": "javascript:alert(1)", "licence": ""}),
           {"id": "c3"}, card(4, evidence="vibes"), card(5), card(5)]
    (folder / "a.json").write_text(json.dumps(bad))
    (folder / "b.json").write_text("not json")
    got, skipped = store.load_cards(tmp_path)
    assert [c["id"] for c in got] == ["c5"] and skipped == 6
    assert store.load_cards(None) == ([], 0) and store.load_cards(tmp_path / "missing") == ([], 0)


def make_env(tmp_path, with_cards=True):
    secrets = tmp_path / "garmin.env"
    secrets.write_text("GARMIN_API_KEY='x'\nGARMIN_API_KEY_EXPIRES_ON=2027-10-22\n")
    rd = tmp_path / "reading"
    if with_cards:
        (rd / "cards").mkdir(parents=True)
        (rd / "cards" / "all.json").write_text(json.dumps(cards(12)))
    app = create_app(Settings(data_dir=tmp_path / "data", secrets_file=secrets, reading_data_dir=rd), FixedClock(D))
    return TestClient(app, base_url="http://127.0.0.1")


def test_api_pick_is_stable_and_status_round_trips(tmp_path):
    with make_env(tmp_path) as client:
        v = client.get("/api/reading").json()
        assert v["available"] and v["today"] and len(v["cards"]) == 12 and v["counts"]["new"] == 11
        today = v["today"]["id"]
        assert client.get("/api/reading").json()["today"]["id"] == today  # kept for the day
        r = client.put(f"/api/reading/{today}", json={"status": "saved"}, headers=MUTATE).json()
        assert r["today"]["status"] == "saved" and r["counts"]["saved"] == 1
        skipped = client.put(f"/api/reading/{today}", json={"status": "skipped"}, headers=MUTATE).json()
        assert skipped["today"]["id"] != today  # skipping frees the slot for another card
        assert client.put("/api/reading/nope", json={"status": "read"}, headers=MUTATE).status_code == 404
        assert client.put(f"/api/reading/{today}", json={"status": "bad"}, headers=MUTATE).status_code == 422
        assert client.put(f"/api/reading/{today}", json={"status": "read"}).status_code == 403  # needs the header


def test_api_without_library_is_empty_not_an_error(tmp_path):
    with make_env(tmp_path, with_cards=False) as client:
        v = client.get("/api/reading").json()
        assert v == {**v, "available": False, "today": None, "cards": []}
