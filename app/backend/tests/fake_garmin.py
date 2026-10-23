"""Synthetic Garmin Personal API: deterministic data, enforced window limits, request counting."""

from __future__ import annotations

import io
import json
import zipfile
from collections import Counter
from datetime import date, timedelta

import httpx

FIRST = date(2025, 9, 1)
FIRST_HRV = date(2026, 1, 1)
HRV_MAX_DAYS = 14
# Real Garmin answers oversized daily-summary windows with HTTP 500, not 400.
SUMMARY_MAX_DAYS = 60


def _days(start: date, end: date):
    d = start
    while d <= end:
        yield d
        d += timedelta(days=1)


def _span_ok(start: date, end: date, limit: int) -> bool:
    return (end - start).days + 1 <= limit


class FakeGarmin:
    def __init__(self, today: date):
        self.today = today
        self.calls: Counter[str] = Counter()
        self.fail_with: int | None = None
        self.forbidden: set[str] = set()

    @property
    def total(self) -> int:
        return sum(self.calls.values())

    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self.handle)

    def activities(self, start: date, end: date) -> list[dict]:
        rows = []
        for d in _days(max(start, FIRST), min(end, self.today)):
            if (d - FIRST).days % 4:
                continue
            rows.append(
                {
                    "activityId": 10_000 + d.toordinal(),
                    "activityName": "Morning Run",
                    "startTimeGMT": f"{d} 06:30:00",
                    "startTimeLocal": f"{d} 12:00:00",
                    "activityType": {"typeKey": "running"},
                    "distance": 5000.0,
                    "duration": 1800.0,
                    "averageHR": 150.0,
                    "activityTrainingLoad": 80.0,
                    "vO2MaxValue": 50.0,
                }
            )
        return sorted(rows, key=lambda r: r["startTimeGMT"], reverse=True)

    def handle(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        q = request.url.params
        if path.endswith("/personal-api-key/token"):
            self.calls["token"] += 1
            return httpx.Response(200, text="h.p.s", headers={"content-type": "text/plain"})
        self.calls[path.split("/")[1] + ":" + path.split("/")[2]] += 1
        if self.fail_with:
            return httpx.Response(self.fail_with)
        if any(path.startswith(p) for p in self.forbidden):
            return httpx.Response(403)

        def window(a: str, b: str) -> tuple[date, date]:
            return date.fromisoformat(a), date.fromisoformat(b)

        if path == "/usersummary-service/v2/dailysummaries":
            s, e = window(q["startDate"], q["endDate"])
            if not _span_ok(s, e, SUMMARY_MAX_DAYS):
                return httpx.Response(500)
            data = []
            for d in _days(s, e):
                real = FIRST <= d <= self.today
                data.append(
                    {
                        "calendarDate": d.isoformat(),
                        "includesWellnessData": real,
                        "movement": {"steps": {"value": 8000 + d.day if real else None}},
                        "heartRate": {"restingValue": 50 if real else None},
                        "stress": {"avgLevel": 30 if real else -1},
                        "bodyBattery": {"maxValue": 90 if real else None},
                        "pulseOx": {"avgValue": 96 if real and d.day % 10 == 0 else None},
                    }
                )
            return httpx.Response(200, json={"data": data})
        if path == "/activitylist-service/activities/search/activities":
            s, e = window(q["startDate"], q["endDate"])
            start, limit = int(q["start"]), int(q["limit"])
            return httpx.Response(200, json=self.activities(s, e)[start : start + limit])
        if path == "/sleep-service/sleep/dailySleepSummariesByDate":
            s, e = window(q["startDate"], q["endDate"])
            if not _span_ok(s, e, 31):
                return httpx.Response(400)
            return httpx.Response(
                200,
                json=[
                    {"calendarDate": d.isoformat(), "sleepTimeSeconds": 27000, "sleepScores": {"overall": {"value": 80}}}
                    for d in _days(max(s, FIRST), min(e, self.today))
                ],
            )
        if path.startswith("/hrv-service/hrv/daily/"):
            s, e = window(*path.rsplit("/", 2)[-2:])
            if not _span_ok(s, e, HRV_MAX_DAYS):
                return httpx.Response(400)
            return httpx.Response(
                200,
                json={
                    "hrvSummaries": [
                        {"calendarDate": d.isoformat(), "lastNightAvg": 60, "weeklyAvg": 58}
                        for d in _days(max(s, FIRST_HRV), min(e, self.today))
                    ]
                },
            )
        if path.startswith("/weight-service/weight/range/"):
            s, e = window(*path.rsplit("/", 2)[-2:])
            summaries = [
                {
                    "summaryDate": d.isoformat(),
                    "allWeightMetrics": [
                        {
                            "calendarDate": d.isoformat(),
                            "timestampGMT": f"{d}T01:30:00.000+0000",
                            "date": f"{d}T07:00:00.000+0530",
                            "weight": 80.0,
                            "bodyFat": 20.0,
                            "muscleMass": 35000,
                            "boneMass": 3200,
                        }
                    ],
                }
                for d in _days(max(s, FIRST), min(e, self.today))
                if d.weekday() == 0
            ]
            return httpx.Response(200, json={"dailyWeightSummaries": summaries})
        if path.startswith("/goal-service/"):
            return httpx.Response(200, json={"userGoals": [], "userGoalRanges": []})
        if path in ("/wellness-service/wellness/bodyBattery/reports/daily",) or path.startswith(
            "/wellnessactivity-service/"
        ):
            return httpx.Response(200, json=[])
        if path == "/userprofile-service/userprofile/settings":
            return httpx.Response(200, json={"measurementSystem": "metric", "timeZone": "Asia/Kolkata"})
        if path == "/biometric-service/heartRateZones/v2":
            return httpx.Response(200, json=[{"sport": "DEFAULT", "zone1Floor": 100}])
        if path.startswith("/download-service/files/activity/"):
            buffer = io.BytesIO()
            with zipfile.ZipFile(buffer, "w") as archive:
                archive.writestr("activity.fit", b"FIT")
            return httpx.Response(200, content=buffer.getvalue(), headers={"content-type": "application/x-zip-compressed"})
        if path.startswith("/activity-service/activity/"):
            return httpx.Response(200, json=[] if path.endswith("/workouts") else {"activityId": 1, "splitSummaries": []})
        if path.startswith("/hrv-service/hrv/"):
            return httpx.Response(200, json={"hrvReadings": [{"hrvValue": 60}]})
        if path.startswith("/wellness-service/wellness/daily/spo2acclimation/"):
            return httpx.Response(200, json={"averageSpO2": 96})
        if path == "/wellness-service/wellness/dailyHeartRate":
            return httpx.Response(200, json={"heartRateValues": [[0, 60]]})
        if path.startswith("/fitnessage-service/"):
            return httpx.Response(200, json=[{"fitnessAge": 30.5}])
        if path.startswith("/periodichealth-service/"):
            return httpx.Response(200, json={})
        if path.startswith("/nutrition-service/"):
            return httpx.Response(404)
        return httpx.Response(404, content=json.dumps({"unexpected": path}))
