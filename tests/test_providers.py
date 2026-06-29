"""Tests for provider payload parsing (pure functions, no network)."""

from __future__ import annotations

from datetime import date

from providers.garmin import GarminProvider, _norm_sport as garmin_sport
from providers.google_fit import GoogleFitProvider
from providers.strava import StravaProvider, _norm_sport as strava_sport
from providers.suunto import SuuntoProvider


def test_garmin_parse_activity():
    p = GarminProvider(email="x", password="y")
    act = {
        "activityId": 12345,
        "activityName": "Trail Run",
        "activityType": {"typeKey": "trail_running"},
        "startTimeLocal": "2025-06-01 07:30:00",
        "duration": 3600.0,
        "distance": 10000.0,
        "averageSpeed": 2.5,  # m/s -> 400 sec/km
        "averageHR": 150,
        "maxHR": 178,
        "calories": 700,
        "elevationGain": 250.0,
        "activityTrainingLoad": 130.0,
        "vO2MaxValue": 49.0,
    }
    rec = p._parse_activity(act, date(2025, 6, 1))
    assert rec.external_id == "12345"
    assert rec.platform == "garmin"
    assert rec.sport_type == "running"
    assert rec.duration_sec == 3600
    assert rec.distance_m == 10000.0
    assert abs(rec.avg_pace_sec_km - 400.0) < 0.01
    assert rec.avg_hr == 150 and rec.max_hr == 178
    assert rec.vo2max_estimate == 49.0


def test_garmin_sport_normalization():
    assert garmin_sport("indoor_cycling") == "cycling"
    assert garmin_sport("strength_training") == "strength"
    assert garmin_sport("unknown_thing") == "unknown_thing"
    assert garmin_sport(None) is None


def test_strava_parse_activity():
    p = StravaProvider(client_id="a", client_secret="b", refresh_token="c")
    act = {
        "id": 987654,
        "name": "Lunch Ride",
        "type": "Ride",
        "sport_type": "Ride",
        "start_date_local": "2025-06-02T12:00:00Z",
        "moving_time": 3600,
        "elapsed_time": 3700,
        "distance": 30000.0,
        "average_speed": 8.333,  # m/s
        "total_elevation_gain": 400.0,
        "average_heartrate": 140.0,
        "max_heartrate": 165.0,
        "average_watts": 210.0,
        "suffer_score": 80,
    }
    rec = p._parse_activity(act)
    assert rec.external_id == "987654"
    assert rec.platform == "strava"
    assert rec.sport_type == "cycling"
    assert rec.duration_sec == 3600
    assert rec.avg_power_w == 210.0
    assert rec.training_load == 80
    assert rec.date == date(2025, 6, 2)


def test_strava_sport_normalization():
    assert strava_sport("TrailRun") == "running"
    assert strava_sport("WeightTraining") == "strength"
    assert strava_sport("Kayaking") == "kayaking"


def test_google_fit_parse_session():
    p = GoogleFitProvider(client_id="a", client_secret="b", refresh_token="c")
    s = {
        "id": "sess-1",
        "name": "Evening Run",
        "activityType": 8,  # running
        "startTimeMillis": "1717225200000",
        "endTimeMillis": "1717228800000",  # +3600s
    }
    rec = p._parse_session(s, distance_m=9500.0, calories=620.0)
    assert rec.platform == "google_fit"
    assert rec.sport_type == "running"
    assert rec.duration_sec == 3600
    assert rec.distance_m == 9500.0
    assert rec.calories == 620


def test_google_fit_parse_sleep():
    p = GoogleFitProvider(client_id="a", client_secret="b", refresh_token="c")
    s = {
        "id": "sleep-1",
        "activityType": 72,
        "startTimeMillis": "1717200000000",
        "endTimeMillis": "1717225200000",  # 7h
    }
    rec = p._parse_sleep(s, stages={"deep": 90, "rem": 100, "light": 200, "awake": 30})
    assert rec.platform == "google_fit"
    assert rec.deep_min == 90 and rec.rem_min == 100
    assert rec.duration_min == 420


def test_suunto_parse_workout():
    p = SuuntoProvider(
        client_id="a", client_secret="b", refresh_token="c", subscription_key="k"
    )
    w = {
        "workoutKey": "abc123",
        "activityId": 1,  # running
        "workoutName": "Tempo",
        "startTime": 1717225200000,
        "totalTime": 1800,
        "totalDistance": 6000.0,
        "totalAscent": 50.0,
        "hravg": 2.5,  # Hz -> 150 bpm
        "hrmax": 3.0,  # Hz -> 180 bpm
        "energyConsumption": 450,
    }
    rec = p._parse_workout(w)
    assert rec.external_id == "abc123"
    assert rec.platform == "suunto"
    assert rec.sport_type == "running"
    assert rec.duration_sec == 1800
    assert rec.avg_hr == 150 and rec.max_hr == 180  # Hz converted to bpm
    assert rec.calories == 450


def test_suunto_hr_already_bpm():
    p = SuuntoProvider(
        client_id="a", client_secret="b", refresh_token="c", subscription_key="k"
    )
    w = {"workoutKey": "x", "activityId": 2, "startTime": 1717225200000, "hravg": 140}
    rec = p._parse_workout(w)
    assert rec.avg_hr == 140  # already bpm, not converted
