"""Strava provider using the official v3 API over OAuth2.

Strava issues short-lived access tokens; we exchange a long-lived refresh token
for a fresh access token on each sync. Strava only exposes activities (no sleep
or HRV), so those methods return empty lists.
"""

from __future__ import annotations

import os
from datetime import date, datetime, time, timezone
from typing import Any, Optional

import httpx

from .base import ActivityRecord, FitnessProvider, HRVRecord, SleepRecord

_TOKEN_URL = "https://www.strava.com/oauth/token"
_API_BASE = "https://www.strava.com/api/v3"

# Strava activity "type"/"sport_type" -> normalized vocabulary.
_SPORT_MAP = {
    "run": "running",
    "trailrun": "running",
    "virtualrun": "running",
    "ride": "cycling",
    "virtualride": "cycling",
    "mountainbikeride": "cycling",
    "gravelride": "cycling",
    "swim": "swimming",
    "walk": "walking",
    "hike": "hiking",
    "weighttraining": "strength",
    "workout": "crossfit",
    "crossfit": "crossfit",
}


def _norm_sport(strava_type: Optional[str]) -> Optional[str]:
    if not strava_type:
        return None
    return _SPORT_MAP.get(strava_type.lower(), strava_type.lower())


class StravaProvider(FitnessProvider):
    def __init__(
        self,
        client_id: Optional[str] = None,
        client_secret: Optional[str] = None,
        refresh_token: Optional[str] = None,
    ):
        self.client_id = client_id or os.environ.get("STRAVA_CLIENT_ID")
        self.client_secret = client_secret or os.environ.get("STRAVA_CLIENT_SECRET")
        self.refresh_token = refresh_token or os.environ.get("STRAVA_REFRESH_TOKEN")
        self._access_token: Optional[str] = None

    @property
    def platform_name(self) -> str:
        return "strava"

    # -- auth --------------------------------------------------------------
    async def authenticate(self) -> bool:
        if not all([self.client_id, self.client_secret, self.refresh_token]):
            raise RuntimeError(
                "Strava credentials missing. Set STRAVA_CLIENT_ID, "
                "STRAVA_CLIENT_SECRET and STRAVA_REFRESH_TOKEN in your .env."
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
        # Strava may rotate the refresh token; surface the new one to the caller.
        new_refresh = payload.get("refresh_token")
        if new_refresh and new_refresh != self.refresh_token:
            self.refresh_token = new_refresh
        return self._access_token is not None

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._access_token}"}

    # -- activities --------------------------------------------------------
    async def get_activities(self, since: date, until: date) -> list[ActivityRecord]:
        if not self._access_token:
            await self.authenticate()
        after = int(datetime.combine(since, time.min, tzinfo=timezone.utc).timestamp())
        before = int(datetime.combine(until, time.max, tzinfo=timezone.utc).timestamp())

        records: list[ActivityRecord] = []
        page = 1
        per_page = 100
        async with httpx.AsyncClient(timeout=60) as client:
            while True:
                resp = await client.get(
                    f"{_API_BASE}/athlete/activities",
                    headers=self._headers(),
                    params={
                        "after": after,
                        "before": before,
                        "page": page,
                        "per_page": per_page,
                    },
                )
                resp.raise_for_status()
                batch = resp.json()
                if not batch:
                    break
                for act in batch:
                    records.append(self._parse_activity(act))
                if len(batch) < per_page:
                    break
                page += 1
        return records

    def _parse_activity(self, act: dict) -> ActivityRecord:
        start_local = act.get("start_date_local") or act.get("start_date")
        act_date = (
            datetime.fromisoformat(start_local.replace("Z", "+00:00")).date()
            if start_local
            else date.today()
        )
        avg_speed = act.get("average_speed")  # m/s
        avg_pace = 1000.0 / avg_speed if avg_speed else None
        moving = act.get("moving_time") or act.get("elapsed_time")
        return ActivityRecord(
            external_id=str(act.get("id")),
            platform="strava",
            date=act_date,
            start_time=start_local,
            sport_type=_norm_sport(act.get("sport_type") or act.get("type")),
            title=act.get("name"),
            duration_sec=int(moving) if moving is not None else None,
            distance_m=act.get("distance"),
            elevation_gain_m=act.get("total_elevation_gain"),
            avg_hr=int(act["average_heartrate"]) if act.get("average_heartrate") else None,
            max_hr=int(act["max_heartrate"]) if act.get("max_heartrate") else None,
            calories=int(act["calories"]) if act.get("calories") else None,
            avg_pace_sec_km=avg_pace,
            avg_power_w=act.get("average_watts"),
            training_load=act.get("suffer_score"),
            vo2max_estimate=None,
            raw_json=act,
        )

    # -- unsupported on Strava --------------------------------------------
    async def get_sleep(self, since: date, until: date) -> list[SleepRecord]:
        return []

    async def get_hrv(self, since: date, until: date) -> list[HRVRecord]:
        return []
