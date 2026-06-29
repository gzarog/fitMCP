"""Google Fit provider using the Fitness REST API over OAuth2.

Activities come from the *sessions* endpoint; distance and calories are enriched
per session via ``dataset:aggregate``. Sleep is read from sleep sessions plus
the ``com.google.sleep.segment`` data type. Google Fit exposes no HRV, so
:meth:`get_hrv` returns an empty list. Weight is read from
``com.google.weight`` for body metrics.

Note: Google has announced the deprecation of the Google Fit APIs. This
provider follows the documented endpoints and is structured so it can be
swapped for Health Connect later without touching the tools layer.
"""

from __future__ import annotations

import os
from datetime import date, datetime, time, timezone
from typing import Any, Optional

import httpx

from .base import (
    ActivityRecord,
    BodyMetricsRecord,
    FitnessProvider,
    HRVRecord,
    SleepRecord,
)

_TOKEN_URL = "https://oauth2.googleapis.com/token"
_API_BASE = "https://www.googleapis.com/fitness/v1/users/me"

# Google Fit numeric activity types -> normalized vocabulary (curated subset;
# anything else falls back to the numeric string).
_SPORT_MAP = {
    1: "cycling",
    7: "walking",
    8: "running",
    9: "crossfit",      # aerobics
    35: "hiking",
    82: "swimming",
    97: "strength",     # weightlifting
    112: "crossfit",    # crossfit
    116: "strength",    # strength training
}

# Sleep segment value -> stage bucket.
_SLEEP_STAGE = {
    1: "awake",
    2: "sleep",   # generic
    3: "awake",   # out of bed
    4: "light",
    5: "deep",
    6: "rem",
}


def _norm_sport(activity_type: Optional[int]) -> Optional[str]:
    if activity_type is None:
        return None
    return _SPORT_MAP.get(activity_type, str(activity_type))


def _ms(d: date, end_of_day: bool = False) -> int:
    t = time.max if end_of_day else time.min
    return int(datetime.combine(d, t, tzinfo=timezone.utc).timestamp() * 1000)


def _ns(d: date, end_of_day: bool = False) -> int:
    return _ms(d, end_of_day) * 1_000_000


class GoogleFitProvider(FitnessProvider):
    def __init__(
        self,
        client_id: Optional[str] = None,
        client_secret: Optional[str] = None,
        refresh_token: Optional[str] = None,
    ):
        self.client_id = client_id or os.environ.get("GOOGLE_CLIENT_ID")
        self.client_secret = client_secret or os.environ.get("GOOGLE_CLIENT_SECRET")
        self.refresh_token = refresh_token or os.environ.get("GOOGLE_REFRESH_TOKEN")
        self._access_token: Optional[str] = None

    @property
    def platform_name(self) -> str:
        return "google_fit"

    # -- auth --------------------------------------------------------------
    async def authenticate(self) -> bool:
        if not all([self.client_id, self.client_secret, self.refresh_token]):
            raise RuntimeError(
                "Google Fit credentials missing. Set GOOGLE_CLIENT_ID, "
                "GOOGLE_CLIENT_SECRET and GOOGLE_REFRESH_TOKEN in your .env."
            )
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                _TOKEN_URL,
                data={
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "grant_type": "refresh_token",
                    "refresh_token": self.refresh_token,
                },
            )
            resp.raise_for_status()
            payload = resp.json()
        self._access_token = payload.get("access_token")
        return self._access_token is not None

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._access_token}"}

    async def _aggregate(
        self,
        client: httpx.AsyncClient,
        data_type: str,
        start_ms: int,
        end_ms: int,
    ) -> list[dict]:
        """Aggregate a data type over a window into a single bucket."""
        resp = await client.post(
            f"{_API_BASE}/dataset:aggregate",
            headers=self._headers(),
            json={
                "aggregateBy": [{"dataTypeName": data_type}],
                "bucketByTime": {"durationMillis": max(end_ms - start_ms, 1)},
                "startTimeMillis": start_ms,
                "endTimeMillis": end_ms,
            },
        )
        resp.raise_for_status()
        buckets = resp.json().get("bucket", [])
        points: list[dict] = []
        for b in buckets:
            for ds in b.get("dataset", []):
                points.extend(ds.get("point", []))
        return points

    # -- activities --------------------------------------------------------
    async def get_activities(self, since: date, until: date) -> list[ActivityRecord]:
        if not self._access_token:
            await self.authenticate()
        records: list[ActivityRecord] = []
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.get(
                f"{_API_BASE}/sessions",
                headers=self._headers(),
                params={
                    "startTime": _iso_z(since, False),
                    "endTime": _iso_z(until, True),
                },
            )
            resp.raise_for_status()
            sessions = resp.json().get("session", [])
            for s in sessions:
                atype = s.get("activityType")
                if atype == 72:  # sleep sessions handled in get_sleep
                    continue
                start_ms = int(s.get("startTimeMillis", 0))
                end_ms = int(s.get("endTimeMillis", 0))
                distance_m = await self._sum_points(
                    client, "com.google.distance.delta", start_ms, end_ms, "fpVal"
                )
                calories = await self._sum_points(
                    client, "com.google.calories.expended", start_ms, end_ms, "fpVal"
                )
                records.append(self._parse_session(s, distance_m, calories))
        return records

    async def _sum_points(
        self, client, data_type, start_ms, end_ms, field
    ) -> Optional[float]:
        try:
            points = await self._aggregate(client, data_type, start_ms, end_ms)
        except Exception:
            return None
        total = 0.0
        found = False
        for p in points:
            for v in p.get("value", []):
                if field in v and v[field] is not None:
                    total += float(v[field])
                    found = True
        return total if found else None

    def _parse_session(
        self, s: dict, distance_m: Optional[float], calories: Optional[float]
    ) -> ActivityRecord:
        start_ms = int(s.get("startTimeMillis", 0))
        end_ms = int(s.get("endTimeMillis", 0))
        start_dt = datetime.fromtimestamp(start_ms / 1000, tz=timezone.utc)
        duration_sec = int((end_ms - start_ms) / 1000) if end_ms > start_ms else None
        return ActivityRecord(
            external_id=str(s.get("id")),
            platform="google_fit",
            date=start_dt.date(),
            start_time=start_dt.isoformat(),
            sport_type=_norm_sport(s.get("activityType")),
            title=s.get("name") or s.get("description"),
            duration_sec=duration_sec,
            distance_m=distance_m,
            calories=int(calories) if calories is not None else None,
            raw_json=s,
        )

    # -- sleep -------------------------------------------------------------
    async def get_sleep(self, since: date, until: date) -> list[SleepRecord]:
        if not self._access_token:
            await self.authenticate()
        records: list[SleepRecord] = []
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.get(
                f"{_API_BASE}/sessions",
                headers=self._headers(),
                params={
                    "startTime": _iso_z(since, False),
                    "endTime": _iso_z(until, True),
                    "activityType": 72,
                },
            )
            resp.raise_for_status()
            for s in resp.json().get("session", []):
                if s.get("activityType") != 72:
                    continue
                start_ms = int(s.get("startTimeMillis", 0))
                end_ms = int(s.get("endTimeMillis", 0))
                stages = await self._sleep_stages(client, start_ms, end_ms)
                records.append(self._parse_sleep(s, stages))
        return records

    async def _sleep_stages(self, client, start_ms, end_ms) -> dict[str, int]:
        """Sum minutes per sleep stage from sleep segment points."""
        try:
            points = await self._aggregate(
                client, "com.google.sleep.segment", start_ms, end_ms
            )
        except Exception:
            return {}
        totals: dict[str, int] = {}
        for p in points:
            seg_start = int(p.get("startTimeNanos", 0))
            seg_end = int(p.get("endTimeNanos", 0))
            minutes = int((seg_end - seg_start) / 1e9 / 60) if seg_end > seg_start else 0
            for v in p.get("value", []):
                stage = _SLEEP_STAGE.get(v.get("intVal"))
                if stage:
                    totals[stage] = totals.get(stage, 0) + minutes
        return totals

    def _parse_sleep(self, s: dict, stages: dict[str, int]) -> SleepRecord:
        start_ms = int(s.get("startTimeMillis", 0))
        end_ms = int(s.get("endTimeMillis", 0))
        start_dt = datetime.fromtimestamp(start_ms / 1000, tz=timezone.utc)
        end_dt = datetime.fromtimestamp(end_ms / 1000, tz=timezone.utc)
        duration_min = int((end_ms - start_ms) / 1000 / 60) if end_ms > start_ms else None
        return SleepRecord(
            external_id=str(s.get("id")),
            platform="google_fit",
            date=start_dt.date(),
            sleep_start=start_dt.isoformat(),
            sleep_end=end_dt.isoformat(),
            duration_min=duration_min,
            deep_min=stages.get("deep"),
            rem_min=stages.get("rem"),
            light_min=stages.get("light"),
            awake_min=stages.get("awake"),
            raw_json=s,
        )

    # -- hrv (unsupported) -------------------------------------------------
    async def get_hrv(self, since: date, until: date) -> list[HRVRecord]:
        return []

    # -- body metrics ------------------------------------------------------
    async def get_body_metrics(self, since: date, until: date) -> list[BodyMetricsRecord]:
        if not self._access_token:
            await self.authenticate()
        records: list[BodyMetricsRecord] = []
        async with httpx.AsyncClient(timeout=60) as client:
            try:
                points = await self._aggregate(
                    client, "com.google.weight", _ms(since), _ms(until, True)
                )
            except Exception:
                points = []
            for p in points:
                weight = None
                for v in p.get("value", []):
                    if "fpVal" in v:
                        weight = round(float(v["fpVal"]), 2)
                if weight is None:
                    continue
                ts_ns = int(p.get("startTimeNanos", 0))
                d = datetime.fromtimestamp(ts_ns / 1e9, tz=timezone.utc).date()
                records.append(
                    BodyMetricsRecord(
                        external_id=d.isoformat(),
                        platform="google_fit",
                        date=d,
                        weight_kg=weight,
                        raw_json=p,
                    )
                )
        return records


def _iso_z(d: date, end_of_day: bool) -> str:
    t = time.max if end_of_day else time.min
    return datetime.combine(d, t, tzinfo=timezone.utc).isoformat().replace("+00:00", "Z")
