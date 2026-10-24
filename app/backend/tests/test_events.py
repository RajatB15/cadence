from datetime import date, datetime, timedelta

from cadence_app import events
from cadence_app.models import Activity
from tests.test_api import MUTATE, env  # noqa: F401  (fixture)


def act(rid: str, day: date, hours: float, km: float | None, gain: float | None = None, hr: float | None = None, hour: int = 8) -> Activity:
    start = datetime(day.year, day.month, day.day, hour)
    return Activity(
        source_id="garmin", source_record_id=rid, start_time_utc=start, timezone="UTC+0", local_date=day,
        activity_type="hiking", name=f"Stage {rid}", duration_s=hours * 3600, distance_m=km * 1000 if km else None,
        avg_hr=hr, elevation_gain_m=gain, imported_at=start,
    )


def test_totals_sum_what_exists_and_leave_missing_as_none():
    d = date(2026, 10, 1)
    acts = [act("1", d, 6, 20, 900, 110), act("2", d + timedelta(days=1), 4, 12, None, 130)]
    t = events.totals(acts)
    assert t["distance_m"] == 32000 and t["duration_s"] == 10 * 3600 and t["elevation_gain_m"] == 900
    assert round(t["avg_hr"], 1) == round((110 * 6 + 130 * 4) / 10, 1)  # weighted by time
    assert t["calories"] is None and t["training_load"] is None  # never reported, not zero
    assert t["elapsed_s"] > t["duration_s"]  # includes the night between stages


def test_split_numbers_days_from_the_first_and_keeps_rest_day_gaps():
    d = date(2026, 10, 1)
    acts = [act("3", d + timedelta(days=2), 5, 15), act("1", d, 6, 20), act("2", d, 1, 3, hour=18)]
    days = events.split(acts)
    assert [(x["number"], x["totals"]["count"]) for x in days] == [(1, 2), (3, 1)]
    assert days[0]["totals"]["distance_m"] == 23000


def test_assemble_reports_links_whose_activity_is_gone():
    out = events.assemble("Trek", [act("1", date(2026, 10, 1), 2, 5)], linked=3, recovery={})
    assert out["missing"] == 2 and out["span_days"] == 1


def _two_runs(client):
    client.post("/api/sync/demo", headers=MUTATE)
    items = client.get("/api/activities?family=run&limit=5").json()["items"]
    return [i["id"] for i in items[:3]]


def test_link_group_survives_rebuild_and_unlink(env):  # noqa: F811
    client, _ = env
    a, b, c = _two_runs(client)
    made = client.post("/api/events", json={"name": " Everest  base camp ", "activity_ids": [a, b]}, headers=MUTATE)
    assert made.status_code == 200
    ev = made.json()
    assert ev["name"] == "Everest base camp" and ev["totals"]["count"] == 2 and ev["missing"] == 0
    # the list and detail show the badge
    assert client.get(f"/api/activities/{a}").json()["activity"]["event"] == {"id": ev["id"], "name": "Everest base camp"}
    assert any(i["event"] for i in client.get("/api/activities?family=run&limit=5").json()["items"])
    # one event per activity
    clash = client.post("/api/events", json={"name": "Other", "activity_ids": [b, c]}, headers=MUTATE)
    assert clash.status_code == 400 and "already in" in clash.json()["detail"]
    assert len(client.get("/api/events").json()["items"]) == 1  # the failed create left nothing behind
    # add another
    assert client.post(f"/api/events/{ev['id']}/activities", json={"activity_ids": [c]}, headers=MUTATE).json()["totals"]["count"] == 3
    # an offline rebuild recreates activity rows (new ids, same Garmin ids): the links must follow
    client.delete("/api/sources/demo/data", headers=MUTATE)
    assert client.get(f"/api/events/{ev['id']}").json()["missing"] == 3
    client.post("/api/sync/demo", headers=MUTATE)
    again = client.get(f"/api/events/{ev['id']}").json()
    assert again["totals"]["count"] == 3 and again["missing"] == 0
    # unlink only on request; the last unlink dissolves the event
    first = again["days"][0]["activities"][0]["id"]
    out = client.delete(f"/api/events/{ev['id']}/activities/{first}", headers=MUTATE).json()["event"]
    assert out["totals"]["count"] == 2
    for day in out["days"]:
        for item in day["activities"]:
            client.delete(f"/api/events/{ev['id']}/activities/{item['id']}", headers=MUTATE)
    assert client.get(f"/api/events/{ev['id']}").status_code == 404


def test_rename_delete_and_validation(env):  # noqa: F811
    client, _ = env
    a, b, _c = _two_runs(client)
    eid = client.post("/api/events", json={"name": "A", "activity_ids": [a]}, headers=MUTATE).json()["id"]
    assert client.patch(f"/api/events/{eid}", json={"name": "B"}, headers=MUTATE).json()["name"] == "B"
    assert client.patch(f"/api/events/{eid}", json={"name": "   "}, headers=MUTATE).status_code in (400, 422)
    assert client.post("/api/events", json={"name": "X", "activity_ids": [999999]}, headers=MUTATE).status_code == 404
    assert client.delete(f"/api/events/{eid}", headers=MUTATE).json() == {"deleted": True}
    assert client.get("/api/activities?family=run&limit=1").json()["items"][0]["event"] is None
