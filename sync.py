"""CLI + shared sync engine for fitness_mcp.

Usage::

    python sync.py --platform all
    python sync.py --platform garmin --from 2025-01-01 --to 2025-06-30
    python sync.py --platform garmin --full-history

The :func:`run_sync` coroutine is also imported by ``tools/sync_tools.py`` so
the MCP ``fitness_sync`` tool and the CLI share one code path.
"""

from __future__ import annotations

import argparse
import asyncio
import time
from datetime import date, datetime, timedelta
from typing import Optional

from dotenv import load_dotenv

from db.database import Database
from providers.base import FitnessProvider
from providers.garmin import GarminProvider
from providers.google_fit import GoogleFitProvider
from providers.strava import StravaProvider
from providers.suunto import SuuntoProvider

load_dotenv()

# Registry: register a new platform here and it works everywhere.
PROVIDERS: dict[str, type[FitnessProvider]] = {
    "garmin": GarminProvider,
    "strava": StravaProvider,
    "google_fit": GoogleFitProvider,
    "suunto": SuuntoProvider,
}

# How far back "--full-history" reaches.
_FULL_HISTORY_START = date(2010, 1, 1)
# Default incremental window when no dates given.
_DEFAULT_DAYS = 30


def _resolve_range(
    since: Optional[str],
    until: Optional[str],
    full_history: bool,
) -> tuple[date, date]:
    today = date.today()
    end = datetime.strptime(until, "%Y-%m-%d").date() if until else today
    if full_history:
        start = _FULL_HISTORY_START
    elif since:
        start = datetime.strptime(since, "%Y-%m-%d").date()
    else:
        start = today - timedelta(days=_DEFAULT_DAYS)
    return start, end


async def sync_provider(
    provider: FitnessProvider,
    db: Database,
    since: date,
    until: date,
) -> dict:
    """Sync a single provider into the database. Returns a result summary."""
    platform = provider.platform_name
    result = {"platform": platform, "records_added": 0, "errors": [], "by_type": {}}
    try:
        await provider.authenticate()
    except Exception as exc:  # noqa: BLE001
        msg = f"auth failed: {exc}"
        result["errors"].append(msg)
        db.record_sync(platform, 0, since, status="error", error_message=msg)
        return result

    fetchers = [
        ("activities", provider.get_activities, db.upsert_activities),
        ("sleep", provider.get_sleep, db.upsert_sleep),
        ("hrv", provider.get_hrv, db.upsert_hrv),
        ("body_metrics", provider.get_body_metrics, db.upsert_body_metrics),
    ]
    for name, fetch, store in fetchers:
        try:
            records = await fetch(since, until)
            n = store(records)
            result["by_type"][name] = n
            result["records_added"] += n
        except Exception as exc:  # noqa: BLE001
            result["errors"].append(f"{name}: {exc}")

    status = "error" if result["errors"] else "ok"
    db.record_sync(
        platform,
        result["records_added"],
        since,
        status=status,
        error_message="; ".join(result["errors"]) or None,
    )
    return result


async def run_sync(
    platform: str = "all",
    since: Optional[str] = None,
    until: Optional[str] = None,
    full_history: bool = False,
    db: Optional[Database] = None,
) -> dict:
    """Sync one or all platforms. Shared by the CLI and the MCP tool."""
    start, end = _resolve_range(since, until, full_history)
    owns_db = db is None
    db = db or Database()

    if platform == "all":
        targets = list(PROVIDERS.keys())
    elif platform in PROVIDERS:
        targets = [platform]
    else:
        if owns_db:
            db.close()
        raise ValueError(
            f"Unknown platform '{platform}'. Known: {', '.join(PROVIDERS) + ', all'}"
        )

    t0 = time.monotonic()
    results = []
    try:
        for name in targets:
            provider = PROVIDERS[name]()
            results.append(await sync_provider(provider, db, start, end))
        # Cross-platform deduplication once everything is written.
        deduped = db_dedup(db)
    finally:
        if owns_db:
            db.close()

    elapsed = round(time.monotonic() - t0, 2)
    total = sum(r["records_added"] for r in results)
    return {
        "date_range": {"from": start.isoformat(), "to": end.isoformat()},
        "elapsed_sec": elapsed,
        "total_records": total,
        "deduped": deduped,
        "platforms": results,
    }


def db_dedup(db: Database) -> int:
    """Mark duplicate activities (same workout on Garmin + Strava).

    Heuristic from the plan: same date + sport, duration and distance within
    5%. Garmin wins (richer metrics); the Strava duplicate's id is recorded in
    the Garmin record's raw_json and the Strava row is removed.

    Returns the number of duplicates removed.
    """
    candidates = db.query(
        """
        SELECT g.id AS garmin_id, s.id AS strava_id,
               g.duration_sec AS g_dur, s.duration_sec AS s_dur,
               g.distance_m AS g_dist, s.distance_m AS s_dist
        FROM activities g
        JOIN activities s
          ON g.platform = 'garmin' AND s.platform = 'strava'
         AND g.date = s.date
         AND g.sport_type IS NOT DISTINCT FROM s.sport_type
        """
    )
    removed = 0
    for row in candidates:
        if not _within_pct(row["g_dur"], row["s_dur"], 0.05):
            continue
        if not _within_pct(row["g_dist"], row["s_dist"], 0.05):
            continue
        db.conn.execute(
            """
            UPDATE activities
            SET raw_json = json_merge_patch(
                COALESCE(raw_json, '{}'),
                json_object('merged_strava_id', ?)
            )
            WHERE id = ?
            """,
            [row["strava_id"], row["garmin_id"]],
        )
        db.conn.execute("DELETE FROM activities WHERE id = ?", [row["strava_id"]])
        removed += 1
    return removed


def _within_pct(a, b, pct: float) -> bool:
    if a is None or b is None:
        # If either lacks the metric, treat as compatible (don't block dedup).
        return True
    if a == 0 and b == 0:
        return True
    larger = max(abs(a), abs(b))
    if larger == 0:
        return True
    return abs(a - b) / larger <= pct


def main() -> None:
    parser = argparse.ArgumentParser(description="Sync fitness data into DuckDB.")
    parser.add_argument(
        "--platform",
        default="all",
        help="garmin | strava | all (default: all)",
    )
    parser.add_argument("--from", dest="since", help="start date YYYY-MM-DD")
    parser.add_argument("--to", dest="until", help="end date YYYY-MM-DD")
    parser.add_argument(
        "--full-history",
        action="store_true",
        help="pull everything from 2010 (use once on first run)",
    )
    args = parser.parse_args()

    result = asyncio.run(
        run_sync(
            platform=args.platform,
            since=args.since,
            until=args.until,
            full_history=args.full_history,
        )
    )

    print(f"\nSync complete in {result['elapsed_sec']}s")
    print(f"Date range: {result['date_range']['from']} -> {result['date_range']['to']}")
    print(f"Total records: {result['total_records']} (deduped {result['deduped']})")
    for p in result["platforms"]:
        line = f"  {p['platform']}: {p['records_added']} records {p['by_type']}"
        if p["errors"]:
            line += f"  ERRORS: {p['errors']}"
        print(line)


if __name__ == "__main__":
    main()
