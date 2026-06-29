"""Suunto provider using the Suunto (Cloud) Partner API over OAuth2.

The public Suunto API exposes *workouts*; sleep and HRV are not available there,
so those methods return empty lists. Requests need both a bearer access token
(refreshed from a long-lived refresh token) and an Ocp-Apim-Subscription-Key.
"""

from __future__ import annotations

import os
from datetime import date, datetime, time, timezone
from typing import Optional

import httpx

from .base import ActivityRecord, FitnessProvider, HRVRecord, SleepRecord

_TOKEN_URL = "https://cloudapi-oauth.suunto.com/oauth/token"
_API_BASE = "https://cloudapi.suunto.com/v2"

# Suunto numeric activity ids -> normalized vocabulary (curated subset).
_SPORT_MAP = {
    1: "running",
    2: "cycling",
    3: "cycling",       # mountain biking
    5: "swimming",
    11: "running",      # trail running
    13: "hiking",
    23: "strength",     # gym / strength
    63: "crossfit",
}


def _norm_sport(activity_id: Optional[int]) -> Optional[str]:
    if activity_id is None:
        return None
    return _SPORT_MAP.get(activity_id, str(activity_id))


def _ms(d: date, end_of_day: bool = False) -> int:
    t = time.max if end_of_day else time.min
    return int(datetime.combine(d, t, tzinfo=timezone.utc).timestamp() * 1000)


class SuuntoProvider(FitnessProvider):
    def __init__(
        self,
        client_id: Optional[str] = None,
        client_secret: Optional[str] = None,
        refresh_token: Optional[str] = None,
        subscription_key: Optional[str] = None,
    ):
        self.client_id = client_id or os.environ.get("SUUNTO_CLIENT_ID")
        self.client_secret = client_secret or os.environ.get("SUUNTO_CLIENT_SECRET")
        self.refresh_token = refresh_token or os.environ.get("SUUNTO_REFRESH_TOKEN")
        self.subscription_key = subscription_key or os.environ.get("SUUNTO_SUBSCRIPTION_KEY")
        self._access_token: Optional[str] = None

    @property
    def platform_name(self) -> str:
        return "suunto"

    # -- auth --------------------------------------------------------------
    async def authenticate(self) -> bool:
        missing = [
            name
            for name, val in [
                ("SUUNTO_CLIENT_ID", self.client_id),
                ("SUUNTO_CLIENT_SECRET", self.client_secret),
                ("SUUNTO_REFRESH_TOKEN", self.refresh_token),
                ("SUUNTO_SUBSCRIPTION_KEY", self.subscription_key),
            ]
            if not val
        ]
        if missing:
            raise RuntimeError(
                "Suunto credentials missing: " + ", ".join(missing) + ". Set them in your .env."
            )
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                _TOKEN_URL,
                data={
                    "grant_type": "refresh_token",
                    "refresh_token": self.refresh_token,
                },
                auth=(self.client_id, self.client_secret),
            )
            resp.raise_for_status()
            payload = resp.json()
        self._access_token = payload.get("access_token")
        new_refresh = payload.get("refresh_token")
        if new_refresh and new_refresh != self.refresh_token:
            self.refresh_token = new_refresh
        return self._access_token is not None

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._access_token}",
            "Ocp-Apim-Subscription-Key": self.subscription_key or "",
        }

    # -- activities --------------------------------------------------------
    async def get_activities(self, since: date, until: date) -> list[ActivityRecord]:
        if not self._access_token:
            await self.authenticate()
        records: list[ActivityRecord] = []
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.get(
                f"{_API_BASE}/workouts",
                headers=self._headers(),
                params={"since": _ms(since), "until": _ms(until, True)},
            )
            resp.raise_for_status()
            body = resp.json()
            workouts = body.get("payload", []) if isinstance(body, dict) else body
            for w in workouts:
                records.append(self._parse_workout(w))
        return records

    def _parse_workout(self, w: dict) -> ActivityRecord:
        start_ms = w.get("startTime") or w.get("startTimeMillis") or 0
        start_dt = datetime.fromtimestamp(int(start_ms) / 1000, tz=timezone.utc)
        total_time = w.get("totalTime")  # seconds
        distance = w.get("totalDistance")  # meters
        avg_hr = w.get("hravg") or w.get("avgHr")
        max_hr = w.get("hrmax") or w.get("maxHr")
        avg_speed = None
        if total_time and distance and total_time > 0:
            avg_speed = distance / total_time  # m/s
        avg_pace = 1000.0 / avg_speed if avg_speed else None
        return ActivityRecord(
            external_id=str(w.get("workoutKey") or w.get("workoutId") or w.get("id")),
            platform="suunto",
            date=start_dt.date(),
            start_time=start_dt.isoformat(),
            sport_type=_norm_sport(w.get("activityId")),
            title=w.get("workoutName") or w.get("activityName"),
            duration_sec=int(total_time) if total_time is not None else None,
            distance_m=float(distance) if distance is not None else None,
            elevation_gain_m=w.get("totalAscent"),
            avg_hr=int(round(avg_hr * 60)) if _is_hz(avg_hr) else (int(avg_hr) if avg_hr else None),
            max_hr=int(round(max_hr * 60)) if _is_hz(max_hr) else (int(max_hr) if max_hr else None),
            calories=int(w["energyConsumption"]) if w.get("energyConsumption") else None,
            avg_pace_sec_km=avg_pace,
            raw_json=w,
        )

    # -- unsupported -------------------------------------------------------
    async def get_sleep(self, since: date, until: date) -> list[SleepRecord]:
        return []

    async def get_hrv(self, since: date, until: date) -> list[HRVRecord]:
        return []


def _is_hz(value) -> bool:
    """Suunto sometimes reports HR in Hz (beats/sec). Heuristic: < 6 means Hz."""
    return isinstance(value, (int, float)) and 0 < value < 6
