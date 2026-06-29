"""Garmin Connect provider backed by the ``garth`` library.

garth is an unofficial Garmin Connect client. We authenticate once and cache
the session token under ``GARTH_HOME`` so subsequent syncs skip the login flow
(which can trigger MFA). All data is fetched through ``garth.connectapi`` raw
endpoints and parsed defensively, because Garmin's private API occasionally
changes field names.
"""

from __future__ import annotations

import asyncio
import os
from datetime import date, datetime, timedelta
from typing import Any, Optional

from .base import (
    ActivityRecord,
    BodyMetricsRecord,
    FitnessProvider,
    HRVRecord,
    SleepRecord,
)

# Garmin sport type strings -> our normalized vocabulary.
_SPORT_MAP = {
    "running": "running",
    "trail_running": "running",
    "treadmill_running": "running",
    "track_running": "running",
    "cycling": "cycling",
    "road_biking": "cycling",
    "mountain_biking": "cycling",
    "indoor_cycling": "cycling",
    "virtual_ride": "cycling",
    "lap_swimming": "swimming",
    "open_water_swimming": "swimming",
    "swimming": "swimming",
    "strength_training": "strength",
    "indoor_cardio": "crossfit",
    "fitness_equipment": "crossfit",
    "hiit": "crossfit",
    "walking": "walking",
    "hiking": "hiking",
    "basketball": "basketball",
}


def _norm_sport(garmin_type: Optional[str]) -> Optional[str]:
    if not garmin_type:
        return None
    key = garmin_type.lower()
    return _SPORT_MAP.get(key, key)


def _parse_dt(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    return value  # Garmin already returns ISO-ish strings; store as-is.


def _date_only(value: Optional[str]) -> Optional[date]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).date()
    except ValueError:
        try:
            return datetime.strptime(value[:10], "%Y-%m-%d").date()
        except ValueError:
            return None


class GarminProvider(FitnessProvider):
    def __init__(
        self,
        email: Optional[str] = None,
        password: Optional[str] = None,
        garth_home: Optional[str] = None,
    ):
        self.email = email or os.environ.get("GARMIN_EMAIL")
        self.password = password or os.environ.get("GARMIN_PASSWORD")
        self.garth_home = os.path.expanduser(
            garth_home or os.environ.get("GARTH_HOME", "~/.garth")
        )
        self._garth = None
        self._display_name: Optional[str] = None

    @property
    def platform_name(self) -> str:
        return "garmin"

    # -- auth --------------------------------------------------------------
    async def authenticate(self) -> bool:
        return await asyncio.to_thread(self._authenticate_sync)

    def _authenticate_sync(self) -> bool:
        import garth

        self._garth = garth
        # Try resuming a cached session first to avoid repeated logins/MFA.
        try:
            garth.resume(self.garth_home)
            # Touch an endpoint to confirm the token is still valid.
            profile = garth.connectapi("/userprofile-service/socialProfile")
            self._display_name = (profile or {}).get("displayName")
            return True
        except Exception:
            pass

        if not self.email or not self.password:
            raise RuntimeError(
                "No valid Garmin session found. Run `python login.py` once to "
                "sign in interactively (your password is never stored) and cache "
                "a session token, or set GARMIN_EMAIL and GARMIN_PASSWORD in .env."
            )
        garth.login(self.email, self.password)
        self._save_session()
        profile = garth.connectapi("/userprofile-service/socialProfile")
        self._display_name = (profile or {}).get("displayName")
        return True

    def login_interactive(self) -> str:
        """Sign in to Garmin at the prompt and cache a session token.

        Reads the password via getpass (never echoed, never written to disk) and
        supports MFA. Returns the resolved Garmin display name on success.
        """
        import getpass

        import garth

        self._garth = garth
        email = self.email or input("Garmin email: ").strip()
        password = self.password or getpass.getpass("Garmin password: ")
        garth.login(email, password, prompt_mfa=lambda: input("MFA code: ").strip())
        self._save_session()
        profile = garth.connectapi("/userprofile-service/socialProfile")
        self._display_name = (profile or {}).get("displayName")
        return self._display_name or email

    def _save_session(self) -> None:
        """Persist the garth token and lock down its file permissions."""
        from security import harden_dir

        self._garth.save(self.garth_home)
        harden_dir(self.garth_home)

    def _api(self, path: str, **params: Any) -> Any:
        return self._garth.connectapi(path, params=params or None)

    # -- activities --------------------------------------------------------
    async def get_activities(self, since: date, until: date) -> list[ActivityRecord]:
        return await asyncio.to_thread(self._get_activities_sync, since, until)

    def _get_activities_sync(self, since: date, until: date) -> list[ActivityRecord]:
        records: list[ActivityRecord] = []
        start = 0
        limit = 50
        while True:
            batch = self._api(
                "/activitylist-service/activities/search/activities",
                start=start,
                limit=limit,
            )
            if not batch:
                break
            stop = False
            for act in batch:
                act_date = _date_only(act.get("startTimeLocal") or act.get("startTimeGMT"))
                if act_date is None:
                    continue
                if act_date < since:
                    # Results are newest-first; once we pass the window, stop.
                    stop = True
                    break
                if act_date > until:
                    continue
                records.append(self._parse_activity(act, act_date))
            if stop or len(batch) < limit:
                break
            start += limit
        return records

    def _parse_activity(self, act: dict, act_date: date) -> ActivityRecord:
        type_key = (act.get("activityType") or {}).get("typeKey")
        duration = act.get("duration")
        distance = act.get("distance")
        avg_speed = act.get("averageSpeed")  # m/s
        avg_pace = None
        if avg_speed and avg_speed > 0:
            avg_pace = 1000.0 / avg_speed  # sec per km
        return ActivityRecord(
            external_id=str(act.get("activityId")),
            platform="garmin",
            date=act_date,
            start_time=_parse_dt(act.get("startTimeLocal")),
            sport_type=_norm_sport(type_key),
            title=act.get("activityName"),
            duration_sec=int(duration) if duration is not None else None,
            distance_m=float(distance) if distance is not None else None,
            elevation_gain_m=act.get("elevationGain"),
            avg_hr=int(act["averageHR"]) if act.get("averageHR") is not None else None,
            max_hr=int(act["maxHR"]) if act.get("maxHR") is not None else None,
            calories=int(act["calories"]) if act.get("calories") is not None else None,
            avg_pace_sec_km=avg_pace,
            avg_power_w=act.get("avgPower"),
            training_load=act.get("activityTrainingLoad"),
            vo2max_estimate=act.get("vO2MaxValue"),
            raw_json=act,
        )

    # -- sleep -------------------------------------------------------------
    async def get_sleep(self, since: date, until: date) -> list[SleepRecord]:
        return await asyncio.to_thread(self._get_sleep_sync, since, until)

    def _get_sleep_sync(self, since: date, until: date) -> list[SleepRecord]:
        records: list[SleepRecord] = []
        display = self._display_name or "me"
        for day in _daterange(since, until):
            try:
                data = self._api(
                    f"/wellness-service/wellness/dailySleepData/{display}",
                    date=day.isoformat(),
                    nonSleepBufferMinutes=60,
                )
            except Exception:
                continue
            if not data:
                continue
            dto = data.get("dailySleepDTO") or {}
            if not dto:
                continue
            scores = dto.get("sleepScores") or {}
            overall = (scores.get("overall") or {}).get("value")
            records.append(
                SleepRecord(
                    external_id=day.isoformat(),
                    platform="garmin",
                    date=day,
                    sleep_start=_epoch_to_iso(dto.get("sleepStartTimestampGMT")),
                    sleep_end=_epoch_to_iso(dto.get("sleepEndTimestampGMT")),
                    duration_min=_sec_to_min(dto.get("sleepTimeSeconds")),
                    score=int(overall) if overall is not None else None,
                    deep_min=_sec_to_min(dto.get("deepSleepSeconds")),
                    rem_min=_sec_to_min(dto.get("remSleepSeconds")),
                    light_min=_sec_to_min(dto.get("lightSleepSeconds")),
                    awake_min=_sec_to_min(dto.get("awakeSleepSeconds")),
                    raw_json=data,
                )
            )
        return records

    # -- hrv + body battery ------------------------------------------------
    async def get_hrv(self, since: date, until: date) -> list[HRVRecord]:
        return await asyncio.to_thread(self._get_hrv_sync, since, until)

    def _get_hrv_sync(self, since: date, until: date) -> list[HRVRecord]:
        records: list[HRVRecord] = []
        for day in _daterange(since, until):
            hrv_summary = None
            try:
                hrv_data = self._api(f"/hrv-service/hrv/{day.isoformat()}")
                hrv_summary = (hrv_data or {}).get("hrvSummary") or {}
            except Exception:
                hrv_data = None
                hrv_summary = {}

            bb_start, bb_end = self._body_battery_for_day(day)

            if not hrv_summary and bb_start is None and bb_end is None:
                continue

            last_night_avg = hrv_summary.get("lastNightAvg")
            records.append(
                HRVRecord(
                    external_id=day.isoformat(),
                    platform="garmin",
                    date=day,
                    rmssd=float(last_night_avg) if last_night_avg is not None else None,
                    sdnn=None,
                    hrv_score=_hrv_status_score(hrv_summary.get("status")),
                    body_battery_start=bb_start,
                    body_battery_end=bb_end,
                    raw_json={"hrv": hrv_data, "body_battery": {"start": bb_start, "end": bb_end}},
                )
            )
        return records

    def _body_battery_for_day(self, day: date) -> tuple[Optional[int], Optional[int]]:
        try:
            report = self._api(
                "/wellness-service/wellness/bodyBattery/reports/daily",
                startDate=day.isoformat(),
                endDate=day.isoformat(),
            )
        except Exception:
            return None, None
        if not report:
            return None, None
        entry = report[0] if isinstance(report, list) else report
        values = (entry or {}).get("bodyBatteryValuesArray") or []
        levels = [v[1] for v in values if isinstance(v, (list, tuple)) and len(v) >= 2 and v[1] is not None]
        if not levels:
            return None, None
        return int(levels[0]), int(levels[-1])

    # -- body metrics ------------------------------------------------------
    async def get_body_metrics(self, since: date, until: date) -> list[BodyMetricsRecord]:
        return await asyncio.to_thread(self._get_body_metrics_sync, since, until)

    def _get_body_metrics_sync(self, since: date, until: date) -> list[BodyMetricsRecord]:
        records: list[BodyMetricsRecord] = []
        for day in _daterange(since, until):
            weight_kg = bmi = None
            try:
                weight = self._api(
                    "/weight-service/weight/dayview/" + day.isoformat()
                )
                summaries = (weight or {}).get("dateWeightList") or []
                if summaries:
                    grams = summaries[0].get("weight")
                    weight_kg = round(grams / 1000.0, 2) if grams else None
                    bmi = summaries[0].get("bmi")
            except Exception:
                pass

            stress_avg = None
            respiration = None
            spo2 = None
            try:
                stress = self._api(f"/wellness-service/wellness/dailyStress/{day.isoformat()}")
                stress_avg = (stress or {}).get("avgStressLevel")
            except Exception:
                pass

            if all(v is None for v in (weight_kg, bmi, stress_avg, respiration, spo2)):
                continue
            records.append(
                BodyMetricsRecord(
                    external_id=day.isoformat(),
                    platform="garmin",
                    date=day,
                    weight_kg=weight_kg,
                    bmi=bmi,
                    stress_avg=int(stress_avg) if stress_avg is not None else None,
                    respiration_avg=respiration,
                    spo2_avg=spo2,
                    raw_json={},
                )
            )
        return records


# -- helpers ---------------------------------------------------------------
def _daterange(since: date, until: date):
    cur = since
    while cur <= until:
        yield cur
        cur += timedelta(days=1)


def _sec_to_min(seconds: Optional[Any]) -> Optional[int]:
    if seconds is None:
        return None
    try:
        return int(round(float(seconds) / 60.0))
    except (TypeError, ValueError):
        return None


def _epoch_to_iso(ms: Optional[Any]) -> Optional[str]:
    if not ms:
        return None
    try:
        return datetime.utcfromtimestamp(float(ms) / 1000.0).isoformat()
    except (TypeError, ValueError, OSError):
        return None


def _hrv_status_score(status: Optional[str]) -> Optional[int]:
    """Map Garmin's textual HRV status to a coarse 0-100 score."""
    if not status:
        return None
    return {
        "POOR": 25,
        "UNBALANCED": 50,
        "LOW": 50,
        "BALANCED": 80,
        "GOOD": 90,
    }.get(status.upper())
