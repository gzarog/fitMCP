"""Abstract provider interface and the dataclasses every provider emits.

To add a new platform: subclass :class:`FitnessProvider`, implement the
abstract methods, and register it in ``sync.py``'s ``PROVIDERS`` dict. Nothing
else in the codebase needs to change — the tools layer reads from DuckDB and is
platform-agnostic.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date
from typing import Optional


@dataclass
class ActivityRecord:
    external_id: str
    platform: str
    date: date
    start_time: Optional[str] = None
    sport_type: Optional[str] = None
    title: Optional[str] = None
    duration_sec: Optional[int] = None
    distance_m: Optional[float] = None
    elevation_gain_m: Optional[float] = None
    avg_hr: Optional[int] = None
    max_hr: Optional[int] = None
    calories: Optional[int] = None
    avg_pace_sec_km: Optional[float] = None
    avg_power_w: Optional[float] = None
    training_load: Optional[float] = None
    vo2max_estimate: Optional[float] = None
    raw_json: dict = field(default_factory=dict)


@dataclass
class SleepRecord:
    external_id: str
    platform: str
    date: date
    sleep_start: Optional[str] = None
    sleep_end: Optional[str] = None
    duration_min: Optional[int] = None
    score: Optional[int] = None
    deep_min: Optional[int] = None
    rem_min: Optional[int] = None
    light_min: Optional[int] = None
    awake_min: Optional[int] = None
    raw_json: dict = field(default_factory=dict)


@dataclass
class HRVRecord:
    external_id: str
    platform: str
    date: date
    rmssd: Optional[float] = None
    sdnn: Optional[float] = None
    hrv_score: Optional[int] = None
    body_battery_start: Optional[int] = None
    body_battery_end: Optional[int] = None
    raw_json: dict = field(default_factory=dict)


@dataclass
class BodyMetricsRecord:
    external_id: str
    platform: str
    date: date
    weight_kg: Optional[float] = None
    bmi: Optional[float] = None
    stress_avg: Optional[int] = None
    respiration_avg: Optional[float] = None
    spo2_avg: Optional[float] = None
    raw_json: dict = field(default_factory=dict)


class FitnessProvider(ABC):
    """Abstract base class for all fitness platform providers.

    To add a new platform: subclass this, implement all abstract methods,
    register in sync.py PROVIDERS dict. Zero other changes needed.
    """

    @property
    @abstractmethod
    def platform_name(self) -> str:
        """Unique platform identifier: 'garmin', 'strava', 'google_fit', 'suunto'."""

    @abstractmethod
    async def authenticate(self) -> bool:
        """Authenticate with the platform. Returns True if successful."""

    @abstractmethod
    async def get_activities(self, since: date, until: date) -> list[ActivityRecord]:
        """Fetch activities in date range."""

    @abstractmethod
    async def get_sleep(self, since: date, until: date) -> list[SleepRecord]:
        """Fetch sleep data in date range."""

    @abstractmethod
    async def get_hrv(self, since: date, until: date) -> list[HRVRecord]:
        """Fetch HRV data in date range."""

    async def get_body_metrics(self, since: date, until: date) -> list[BodyMetricsRecord]:
        """Fetch body metrics. Optional — return empty list if not supported."""
        return []
