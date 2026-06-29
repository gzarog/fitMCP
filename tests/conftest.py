"""Shared pytest fixtures: an isolated temp DuckDB seeded with sample data."""

from __future__ import annotations

import json
from datetime import date, timedelta

import pytest

from db.database import Database
from providers.base import ActivityRecord, HRVRecord, SleepRecord


@pytest.fixture
def db_path(tmp_path, monkeypatch):
    """Point DUCKDB_PATH at a per-test temp file."""
    p = tmp_path / "test.duckdb"
    monkeypatch.setenv("DUCKDB_PATH", str(p))
    return str(p)


@pytest.fixture
def db(db_path):
    """An open read-write Database (caller may use directly)."""
    d = Database()
    yield d
    d.close()


@pytest.fixture
def today():
    return date.today()


@pytest.fixture
def seeded(db_path, today):
    """Seed a temp DB and close the writer so tools can read it.

    Returns the db path. A Garmin/Strava duplicate pair is intentionally
    included so dedup tests have something to collapse.
    """
    d = Database()
    d.upsert_activities(
        [
            ActivityRecord(
                external_id="1", platform="garmin", date=today, sport_type="running",
                title="Morning Run", duration_sec=3000, distance_m=10000.0,
                avg_hr=150, max_hr=175, calories=600, training_load=120.0,
                vo2max_estimate=48.0, avg_pace_sec_km=300.0, elevation_gain_m=120.0,
                raw_json={"a": 1},
            ),
            ActivityRecord(
                external_id="1", platform="strava", date=today, sport_type="running",
                title="Morning Run", duration_sec=3010, distance_m=10050.0,
                avg_hr=149, raw_json={"b": 2},
            ),
            ActivityRecord(
                external_id="2", platform="garmin", date=today - timedelta(days=2),
                sport_type="cycling", title="Ride", duration_sec=3600,
                distance_m=30000.0, avg_hr=130, training_load=90.0, raw_json={},
            ),
        ]
    )
    d.upsert_sleep(
        [
            SleepRecord(
                external_id=today.isoformat(), platform="garmin", date=today,
                duration_min=420, score=82, deep_min=90, rem_min=100,
                light_min=210, awake_min=20, raw_json={},
            )
        ]
    )
    d.upsert_hrv(
        [
            HRVRecord(
                external_id=today.isoformat(), platform="garmin", date=today,
                rmssd=55.0, hrv_score=80, body_battery_start=30,
                body_battery_end=85, raw_json={},
            )
        ]
    )
    d.record_sync("garmin", 5, today - timedelta(days=30))
    d.close()
    return db_path


def call_tool(name: str, args: dict) -> dict:
    """Invoke a registered MCP tool and parse its JSON envelope."""
    import asyncio

    import server

    out = asyncio.run(server.mcp.call_tool(name, args))
    return json.loads(out[0].text)
