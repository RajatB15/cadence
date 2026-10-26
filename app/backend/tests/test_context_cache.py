from datetime import date, timedelta

from cadence_app.analytics import insights
from cadence_app.db import make_engine, make_session_factory, upgrade_database
from tests.test_api import MUTATE, env  # noqa: F401  (fixture)


def test_context_is_built_once_until_something_changes(env, monkeypatch):  # noqa: F811
    client, clock = env
    client.post("/api/sync/demo", headers=MUTATE)
    builds = []
    real = insights.build_context
    monkeypatch.setattr(insights, "build_context", lambda *a, **k: builds.append(1) or real(*a, **k))
    insights.invalidate_context()
    client.get("/api/overview")
    client.get("/api/overview")
    client.get("/api/insights")
    assert len(builds) == 1  # three pages, one build
    client.put(f"/api/wellbeing/{clock.today()}", json={"illness": 2}, headers=MUTATE)  # a write drops the cache
    client.get("/api/overview")
    assert len(builds) == 2
    client.post("/api/time-off", json={"kind": "sick", "start": str(clock.today() - timedelta(days=1))}, headers=MUTATE)
    assert client.get("/api/overview").json()["coach"]["week"]["time_off"] is not None and len(builds) == 3


def test_callers_get_their_own_copy(tmp_path, monkeypatch):
    url = f"sqlite:///{tmp_path / 'c.db'}"
    upgrade_database(url)
    monkeypatch.setattr(insights, "build_context", lambda *a, **k: {"as_of": 1, "shared": {}})
    insights.invalidate_context()
    with make_session_factory(make_engine(url))() as session:
        a = insights.context(session, "demo", date(2026, 1, 1))
        a["scratch"] = 1
        a["_phase"][date(2026, 1, 5)] = "memo"  # the phase memo is shared on purpose
        b = insights.context(session, "demo", date(2026, 1, 1))
        assert "scratch" not in b and b["_phase"] == a["_phase"]
        assert insights.context(session, "demo", date(2026, 1, 2))["as_of"] == 1  # another day is rebuilt, not reused
