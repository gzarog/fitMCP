-- schema.sql

CREATE TABLE IF NOT EXISTS activities (
    id                VARCHAR PRIMARY KEY,  -- platform:external_id
    platform          VARCHAR NOT NULL,     -- 'garmin' | 'strava' | 'google_fit' | 'suunto'
    external_id       VARCHAR NOT NULL,
    date              DATE NOT NULL,
    start_time        TIMESTAMP,
    sport_type        VARCHAR,              -- 'running' | 'cycling' | 'crossfit' | 'basketball' etc
    title             VARCHAR,
    duration_sec      INTEGER,
    distance_m        DOUBLE,
    elevation_gain_m  DOUBLE,
    avg_hr            INTEGER,
    max_hr            INTEGER,
    calories          INTEGER,
    avg_pace_sec_km   DOUBLE,              -- for running
    avg_power_w       DOUBLE,              -- for cycling
    training_load     DOUBLE,              -- platform-specific load score
    vo2max_estimate   DOUBLE,
    raw_json          JSON,                -- full original payload
    created_at        TIMESTAMP DEFAULT now()
);

CREATE TABLE IF NOT EXISTS sleep (
    id                VARCHAR PRIMARY KEY,
    platform          VARCHAR NOT NULL,
    date              DATE NOT NULL,       -- night of sleep (start date)
    sleep_start       TIMESTAMP,
    sleep_end         TIMESTAMP,
    duration_min      INTEGER,
    score             INTEGER,             -- 0-100 platform sleep score
    deep_min          INTEGER,
    rem_min           INTEGER,
    light_min         INTEGER,
    awake_min         INTEGER,
    raw_json          JSON,
    created_at        TIMESTAMP DEFAULT now()
);

CREATE TABLE IF NOT EXISTS hrv (
    id                VARCHAR PRIMARY KEY,
    platform          VARCHAR NOT NULL,
    date              DATE NOT NULL,
    rmssd             DOUBLE,             -- ms
    sdnn              DOUBLE,             -- ms
    hrv_score         INTEGER,            -- platform-specific 0-100
    body_battery_start INTEGER,           -- Garmin specific
    body_battery_end   INTEGER,
    raw_json          JSON,
    created_at        TIMESTAMP DEFAULT now()
);

CREATE TABLE IF NOT EXISTS body_metrics (
    id                VARCHAR PRIMARY KEY,
    platform          VARCHAR NOT NULL,
    date              DATE NOT NULL,
    weight_kg         DOUBLE,
    bmi               DOUBLE,
    stress_avg        INTEGER,
    respiration_avg   DOUBLE,
    spo2_avg          DOUBLE,
    raw_json          JSON,
    created_at        TIMESTAMP DEFAULT now()
);

CREATE TABLE IF NOT EXISTS sync_log (
    platform          VARCHAR PRIMARY KEY,
    last_sync_at      TIMESTAMP,
    last_sync_from    DATE,               -- earliest date synced
    records_added     INTEGER DEFAULT 0,
    status            VARCHAR DEFAULT 'ok', -- 'ok' | 'error'
    error_message     VARCHAR
);

-- Useful indexes
CREATE INDEX IF NOT EXISTS idx_activities_date ON activities(date DESC);
CREATE INDEX IF NOT EXISTS idx_activities_sport ON activities(sport_type);
CREATE INDEX IF NOT EXISTS idx_sleep_date ON sleep(date DESC);
CREATE INDEX IF NOT EXISTS idx_hrv_date ON hrv(date DESC);
