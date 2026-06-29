"""End-to-end tests exercising MCP tools against a seeded temp DB."""

from __future__ import annotations

from datetime import timedelta

from .conftest import call_tool


def _range(today):
    return (today - timedelta(days=7)).isoformat(), today.isoformat()


def test_sync_status(seeded):
    res = call_tool("fitness_sync_status", {})
    assert res["success"]
    platforms = {r["platform"] for r in res["data"]}
    assert "garmin" in platforms


def test_database_stats(seeded):
    res = call_tool("fitness_get_database_stats", {})
    assert res["success"]
    assert res["data"]["tables"]["activities"]["rows"] >= 1


def test_get_activities_pagination(seeded, today):
    fr, to = _range(today)
    res = call_tool("fitness_get_activities", {"date_from": fr, "date_to": to, "limit": 1})
    assert res["success"]
    assert len(res["data"]) == 1
    assert res["meta"]["total"] >= 2


def test_get_activities_sport_filter(seeded, today):
    fr, to = _range(today)
    res = call_tool(
        "fitness_get_activities",
        {"date_from": fr, "date_to": to, "sport_type": "cycling"},
    )
    assert res["success"]
    assert all(a["sport_type"] == "cycling" for a in res["data"])


def test_activity_detail_and_missing(seeded):
    ok = call_tool("fitness_get_activity_detail", {"activity_id": "garmin:1"})
    assert ok["success"] and ok["data"]["id"] == "garmin:1"
    missing = call_tool("fitness_get_activity_detail", {"activity_id": "garmin:doesnotexist"})
    assert missing["success"] is False


def test_personal_bests(seeded):
    res = call_tool("fitness_get_personal_bests", {"sport_type": "running"})
    assert res["success"]
    # Both Garmin (10000m) and its Strava duplicate (10050m) are present here
    # (dedup is a separate step); the tool must return the true maximum.
    assert res["data"]["longest_distance"]["distance_m"] == 10050.0
    assert res["data"]["highest_max_hr"]["id"] == "garmin:1"


def test_sleep_and_recovery(seeded, today):
    fr, to = _range(today)
    sleep = call_tool("fitness_get_sleep", {"date_from": fr, "date_to": to})
    assert sleep["success"] and len(sleep["data"]) == 1
    rec = call_tool("fitness_get_recovery_status", {"date": "today"})
    assert rec["success"]
    assert rec["data"]["hrv"]["rmssd"] == 55.0
    assert rec["data"]["sleep"]["sleep_score"] == 82


def test_training_and_summary(seeded):
    load = call_tool("fitness_get_training_load", {"weeks": 4})
    assert load["success"]
    summary = call_tool("fitness_get_weekly_summary", {"week_offset": 0})
    assert summary["success"]
    assert "by_sport" in summary["data"]


def test_trends_and_compare(seeded, today):
    fr, to = _range(today)
    trends = call_tool(
        "fitness_get_trends",
        {"metric": "training_load", "date_from": fr, "date_to": to, "granularity": "week"},
    )
    assert trends["success"]
    cmp = call_tool(
        "fitness_compare_platforms", {"metric": "activities", "date_from": fr, "date_to": to}
    )
    assert cmp["success"]


def test_correlate(seeded, today):
    fr, to = _range(today)
    res = call_tool(
        "fitness_correlate",
        {"metric_a": "sleep_score", "metric_b": "hrv", "date_from": fr, "date_to": to},
    )
    assert res["success"]
    assert res["data"]["n"] >= 1
