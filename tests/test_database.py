"""Tests for the DuckDB layer: schema, upsert idempotency, dedup, sync log."""

from __future__ import annotations

from datetime import date, timedelta

from db.database import Database
from providers.base import ActivityRecord
from sync import _within_pct, db_dedup


def test_schema_initialized(db):
    tables = {r["name"] for r in db.query("SHOW TABLES")}
    assert {"activities", "sleep", "hrv", "body_metrics", "sync_log"} <= tables


def test_upsert_is_idempotent(db, today):
    rec = ActivityRecord(
        external_id="42", platform="garmin", date=today,
        sport_type="running", duration_sec=100, raw_json={"v": 1},
    )
    db.upsert_activities([rec])
    db.upsert_activities([rec])  # same id => update, not duplicate
    rows = db.query("SELECT * FROM activities WHERE id = 'garmin:42'")
    assert len(rows) == 1
    assert rows[0]["id"] == "garmin:42"


def test_upsert_updates_existing(db, today):
    rec = ActivityRecord(external_id="7", platform="garmin", date=today, duration_sec=100, raw_json={})
    db.upsert_activities([rec])
    rec.duration_sec = 999
    db.upsert_activities([rec])
    rows = db.query("SELECT duration_sec FROM activities WHERE id = 'garmin:7'")
    assert rows[0]["duration_sec"] == 999


def test_raw_json_roundtrip(db, today):
    rec = ActivityRecord(external_id="9", platform="garmin", date=today, raw_json={"k": [1, 2, 3]})
    db.upsert_activities([rec])
    rows = db.query("SELECT raw_json::VARCHAR AS rj FROM activities WHERE id = 'garmin:9'")
    assert "k" in rows[0]["rj"]


def test_record_sync(db, today):
    db.record_sync("garmin", 12, today)
    rows = db.query("SELECT * FROM sync_log WHERE platform = 'garmin'")
    assert rows[0]["records_added"] == 12
    assert rows[0]["status"] == "ok"


def test_dedup_collapses_matching_pair(seeded):
    d = Database()
    before = d.query("SELECT COUNT(*) AS n FROM activities")[0]["n"]
    removed = db_dedup(d)
    after = d.query("SELECT COUNT(*) AS n FROM activities")[0]["n"]
    assert before == 3 and removed == 1 and after == 2
    # Strava row gone; Garmin row keeps merged id.
    assert d.query("SELECT COUNT(*) AS n FROM activities WHERE platform='strava'")[0]["n"] == 0
    merged = d.query("SELECT raw_json::VARCHAR AS rj FROM activities WHERE id='garmin:1'")[0]["rj"]
    assert "merged_strava_id" in merged
    d.close()


def test_within_pct():
    assert _within_pct(100, 104, 0.05) is True
    assert _within_pct(100, 110, 0.05) is False
    assert _within_pct(None, 100, 0.05) is True  # missing metric doesn't block
    assert _within_pct(0, 0, 0.05) is True
