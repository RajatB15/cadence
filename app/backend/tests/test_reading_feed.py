from datetime import date, datetime

import httpx
from fastapi.testclient import TestClient

from cadence_app import reading_feed as F
from cadence_app.config import Settings
from cadence_app.db import make_engine, make_session_factory, upgrade_database
from cadence_app.main import create_app
from tests.test_api import MUTATE, FixedClock

TODAY, NOW = date(2026, 10, 22), datetime(2026, 10, 22, 9, 0)
LONG = ("Background: Athletes often ask about this. " * 8) + "Conclusions: Evidence is limited."


def result(rid="1", title="Protein intake, sleep, training load, mental fatigue and mental health in athletes: a meta-analysis.", abstract=LONG, types=("Meta-Analysis", "Journal Article"), **kw):
    return {"id": rid, "source": "MED", "pmid": rid, "doi": f"10.1/{rid}", "title": title, "abstractText": abstract,
            "journalTitle": "Synthetic Journal", "firstPublicationDate": "2026-10-10", "license": "cc by",
            "pubTypeList": {"pubType": list(types)}, **kw}


def test_parse_labels_evidence_and_cleans_text():
    row = F.parse(result(abstract="<h4>Background</h4>" + LONG), "nutrition", NOW)
    assert row["evidence"] == "review" and row["id"] == "epmc:MED:1" and row["url"] == "https://doi.org/10.1/1"
    assert row["licence"] == "CC BY" and "<" not in row["snippet"] and len(row["snippet"]) <= F.SNIPPET_CHARS + 1
    assert F.parse(result(types=("Randomized Controlled Trial",)), "nutrition", NOW)["evidence"] == "trial"
    assert F.parse(result(types=("Practice Guideline", "Meta-Analysis")), "nutrition", NOW)["evidence"] == "guideline"


def test_parse_drops_what_we_cannot_stand_behind():
    assert F.parse(result(types=("research-article",)), "nutrition", NOW) is None  # no type we can label
    assert F.parse(result(types=("Meta-Analysis", "Retracted Publication")), "nutrition", NOW) is None
    assert F.parse(result(title="Protein intake in mice: a meta-analysis"), "nutrition", NOW) is None
    assert F.parse(result(title="Protein intake in dialysis patients"), "nutrition", NOW) is None
    assert F.parse(result(abstract="Too short."), "nutrition", NOW) is None
    assert F.parse(result(title="Unrelated topic entirely", abstract="Lorem ipsum dolor. " * 20), "nutrition", NOW) is None
    assert F.parse({**result(), "firstPublicationDate": None}, "nutrition", NOW) is None


def test_query_is_bounded_and_open_access():
    q = F.query_for("recovery", TODAY)
    assert "OPEN_ACCESS:y" in q and "FIRST_PDATE:[2026-06-24 TO 2026-10-22]" in q and "Meta-Analysis" in q


def fake(results_by_call=None, fail_topics=()):
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        q = request.url.params["query"]
        if any(t in q for t in fail_topics):
            return httpx.Response(500)
        n = len(seen)
        return httpx.Response(200, json={"resultList": {"result": results_by_call(n) if results_by_call else [result(str(n))]}})

    return httpx.Client(transport=httpx.MockTransport(handler)), seen


def factory_for(tmp_path):
    url = f"sqlite:///{tmp_path / 'x.sqlite3'}"
    upgrade_database(url)
    return make_session_factory(make_engine(url))


def test_refresh_stores_items_and_waits_between_runs(tmp_path):
    factory = factory_for(tmp_path)
    http, seen = fake(lambda n: [result(str(n * 10 + i)) for i in range(12)])
    stored = F.refresh(factory, TODAY, NOW, http)
    assert stored == len(F.TOPIC_QUERIES) * F.PER_TOPIC and len(seen) == len(F.TOPIC_QUERIES)
    with factory() as s:
        assert not F.due(s, NOW) and F.due(s, datetime(2026, 10, 26, 9))
    assert F.refresh(factory, TODAY, NOW, http) == 0 and len(seen) == len(F.TOPIC_QUERIES)  # not due, no requests


def test_failed_topic_keeps_old_items_and_total_failure_retries(tmp_path):
    factory = factory_for(tmp_path)
    http, _ = fake()
    F.refresh(factory, TODAY, NOW, http)
    later = datetime(2026, 10, 30, 9)
    flaky, _ = fake(lambda n: [result(f"new{n}")], fail_topics=("durability",))
    F.refresh(factory, TODAY, later, flaky, force=True)
    with factory() as s:
        from cadence_app.models import ReadingFeedItem
        by_topic = {r.topic for r in s.query(ReadingFeedItem)}
        assert "sports-science" in by_topic  # the failed topic kept what it had
        assert F.state(s)["failed"] == ["sports-science"]
    dead = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(503)))
    with factory() as s:
        before = F.state(s).get("fetched_at")
    F.refresh(factory, TODAY, datetime(2026, 11, 5, 9), dead, force=True)
    with factory() as s:
        assert F.state(s).get("fetched_at") == before  # nothing recorded, so it tries again


def test_disabled_feed_makes_no_requests(tmp_path):
    factory = factory_for(tmp_path)
    with factory() as s:
        F.set_enabled(s, False)
    http, seen = fake()
    assert F.refresh(factory, TODAY, NOW, http, force=True) == 0 and not seen


def test_api_feed_items_state_and_setting(tmp_path):
    secrets = tmp_path / "garmin.env"
    secrets.write_text("GARMIN_API_KEY='x'\nGARMIN_API_KEY_EXPIRES_ON=2027-10-22\n")
    app = create_app(Settings(data_dir=tmp_path / "data", secrets_file=secrets), FixedClock(TODAY))
    with TestClient(app, base_url="http://127.0.0.1") as client:
        v = client.get("/api/reading").json()
        assert v["feed"] == {"available": False, "enabled": True, "fetched_at": None, "items": []}
        assert client.post("/api/reading/feed/refresh", headers=MUTATE).status_code == 409  # off for this server
        assert client.put("/api/settings/reading-feed", json={"enabled": False}, headers=MUTATE).json()["enabled"] is False
        from cadence_app.models import ReadingFeedItem
        with make_session_factory(make_engine(f"sqlite:///{tmp_path / 'data' / 'cadence.sqlite3'}"))() as s:
            s.add(ReadingFeedItem(**F.parse(result("77"), "nutrition", NOW)))
            s.commit()
        items = client.get("/api/reading").json()["feed"]["items"]
        assert [i["id"] for i in items] == ["epmc:MED:77"]
        assert client.put("/api/reading/epmc:MED:77", json={"status": "saved"}, headers=MUTATE).status_code == 200
        client.put("/api/reading/epmc:MED:77", json={"status": "skipped"}, headers=MUTATE)
        assert client.get("/api/reading").json()["feed"]["items"] == []  # dismissed items are hidden
