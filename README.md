# fitness_mcp

A generic, multi-platform fitness MCP server. It pulls data from **Garmin
Connect**, **Strava**, **Google Fit**, and **Suunto**, stores everything locally
in a single **DuckDB** file, and exposes analytics as **MCP tools** over stdio —
usable from Claude Desktop, Cursor, Windsurf, VS Code, or any MCP client.

- **Zero running infrastructure** — sync is manual, the server runs on demand.
- **Fully extensible** — adding a platform = implement one abstract class and
  register it. The tools layer never changes.
- **Read-only by design** — MCP tools only read; `fitness_query` enforces
  SELECT-only.

## Architecture

```
server.py        MCP entry point (stdio)         providers/base.py     abstract interface + dataclasses
sync.py          CLI + shared sync engine        providers/garmin.py   Garmin Connect (garth)
db/database.py   DuckDB connection + upserts      providers/strava.py   Strava (OAuth2 + httpx)
db/schema.sql    table definitions               tools/*.py            MCP tools (activities, health, …)
```

Data flow: `providers` fetch normalized records → `db` upserts them into DuckDB
→ `tools` query DuckDB and return a uniform JSON envelope.

Every tool returns:

```json
{ "success": true, "data": [...], "error": null, "meta": { "count": 42 } }
```

## Setup

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # then fill in credentials
```

### Credentials (`.env`)

```bash
DUCKDB_PATH=./fitness.duckdb

# Garmin Connect (via garth)
GARMIN_EMAIL=your@email.com
GARMIN_PASSWORD=yourpassword
GARTH_HOME=~/.garth          # cached session token lives here

# Strava
STRAVA_CLIENT_ID=...
STRAVA_CLIENT_SECRET=...
STRAVA_REFRESH_TOKEN=...
```

`.env` and the DuckDB file are gitignored.

#### Strava: getting a refresh token (one time)

1. Create an API application at <https://www.strava.com/settings/api>. Note the
   **Client ID** and **Client Secret**.
2. Authorize your own account, requesting the `activity:read_all` scope. Visit
   (replace `CLIENT_ID`):

   ```
   https://www.strava.com/oauth/authorize?client_id=CLIENT_ID&response_type=code&redirect_uri=http://localhost&approval_prompt=force&scope=activity:read_all
   ```

   After approving, the browser redirects to `http://localhost/?...&code=AUTH_CODE&...`.
   Copy `AUTH_CODE` from the URL.
3. Exchange the code for tokens:

   ```bash
   curl -X POST https://www.strava.com/oauth/token \
     -d client_id=CLIENT_ID -d client_secret=CLIENT_SECRET \
     -d code=AUTH_CODE -d grant_type=authorization_code
   ```

   Put the `refresh_token` from the response into `STRAVA_REFRESH_TOKEN`. The
   server refreshes the short-lived access token automatically on every sync.

> Garmin uses `garth`, which logs in with your email/password and caches a
> session token under `GARTH_HOME`. The first login may prompt for MFA; after
> that, syncs reuse the cached token.

## Syncing data

```bash
python sync.py --platform all                          # last 30 days, all platforms
python sync.py --platform garmin                       # garmin | strava | google_fit | suunto
python sync.py --platform garmin --from 2025-01-01 --to 2025-06-30
python sync.py --platform garmin --full-history        # everything from 2010 (first run)
```

Supported platforms: `garmin`, `strava`, `google_fit`, `suunto`. Garmin is the
richest source (activities, sleep, HRV, body battery, stress); Strava and Suunto
provide activities; Google Fit provides activities, sleep, and weight.

After all platforms sync, duplicate workouts (same day + sport, duration and
distance within 5%) are de-duplicated: the Garmin record is kept (richer
metrics) and the Strava id is merged into its `raw_json`.

## Running the MCP server

```bash
python server.py        # serves over stdio
```

### Claude Desktop config

`~/Library/Application Support/Claude/claude_desktop_config.json` (macOS) or
`%APPDATA%\Claude\claude_desktop_config.json` (Windows):

```json
{
  "mcpServers": {
    "fitness": {
      "command": "/absolute/path/to/fitness-mcp/.venv/bin/python",
      "args": ["/absolute/path/to/fitness-mcp/server.py"],
      "env": { "PYTHONPATH": "/absolute/path/to/fitness-mcp" }
    }
  }
}
```

## MCP tools

| Tool | Purpose |
|---|---|
| `fitness_sync(platform)` | Sync garmin/strava/all into DuckDB |
| `fitness_sync_status()` | Last sync time + record counts per platform |
| `fitness_get_database_stats()` | Row counts, date ranges, file size |
| `fitness_get_activities(date_from, date_to, platform, sport_type, limit, offset)` | Paginated activity list |
| `fitness_get_activity_detail(activity_id)` | Full detail incl. raw payload |
| `fitness_get_personal_bests(sport_type)` | Longest, fastest, max HR, most elevation |
| `fitness_get_sleep(date_from, date_to, platform)` | Sleep records |
| `fitness_get_hrv(date_from, date_to, platform)` | HRV + body battery |
| `fitness_get_body_battery(date_from, date_to)` | Body battery trend |
| `fitness_get_recovery_status(date)` | One-day recovery snapshot |
| `fitness_get_training_load(weeks, platform)` | Weekly load trend |
| `fitness_get_vo2max_trend(months)` | VO2max estimates over time |
| `fitness_get_weekly_summary(week_offset)` | Week totals + sport split |
| `fitness_get_sport_breakdown(date_from, date_to)` | Time/distance/count per sport |
| `fitness_compare_platforms(metric, date_from, date_to)` | Same metric per platform |
| `fitness_correlate(metric_a, metric_b, date_from, date_to)` | Pearson correlation + scatter |
| `fitness_get_trends(metric, date_from, date_to, granularity)` | Time series by day/week/month |
| `fitness_query(sql)` | Read-only SELECT against the database |

Metrics for `fitness_correlate` / `fitness_get_trends`: `sleep_score`,
`sleep_duration`, `hrv`, `hrv_score`, `body_battery`, `training_load`,
`distance`, `duration`, `avg_hr`, `stress`, `weight`.

## Tests

```bash
pip install -r requirements-dev.txt
PYTHONPATH=. pytest
```

The suite covers the DuckDB layer (upsert idempotency, dedup, sync log),
provider payload parsing for all four platforms, the read-only SQL guard, and
every MCP tool end-to-end against a seeded temp database — no network or
credentials required. CI runs it on every push and pull request
(`.github/workflows/tests.yml`).

## Adding a new platform

1. Create `providers/newplatform.py` extending `FitnessProvider`.
2. Add credentials to `.env`.
3. Register it in `sync.py`: `PROVIDERS["newplatform"] = NewPlatformProvider`.

Done — every tool includes it automatically when `platform="all"`.

## Project status

Implemented: foundation, all four providers (Garmin, Strava, Google Fit,
Suunto), cross-platform dedup, the full tools layer (activities, health,
training, analysis, sync), and a pytest suite with CI. Google Fit has no HRV and
Suunto exposes only workouts via its public API; both still satisfy the common
`FitnessProvider` interface, so the tools layer treats them uniformly.
