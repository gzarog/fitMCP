"""Tests for the scheduled sync runner's logging/summary helpers."""

from __future__ import annotations

from datetime import datetime

from scripts.scheduled_sync import count_errors, format_log_line

_RESULT = {
    "total_records": 42,
    "deduped": 3,
    "elapsed_sec": 5.1,
    "platforms": [
        {"platform": "garmin", "records_added": 40, "errors": []},
        {"platform": "strava", "records_added": 2, "errors": ["activities: boom"]},
    ],
}


def test_format_log_line():
    when = datetime(2026, 6, 29, 7, 0, 0)
    line = format_log_line(_RESULT, when)
    assert line.startswith("2026-06-29T07:00:00")
    assert "total=42" in line
    assert "deduped=3" in line
    assert "garmin=40" in line and "strava=2" in line
    assert "errors=1" in line
    assert "elapsed=5.1s" in line


def test_count_errors():
    assert count_errors(_RESULT) == 1
    assert count_errors({"platforms": []}) == 0
    assert count_errors({}) == 0


def test_format_log_line_empty():
    line = format_log_line({})
    assert "total=0" in line and "errors=0" in line and "[]" in line
