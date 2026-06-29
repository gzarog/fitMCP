"""MCP tools: trigger sync, check sync status, database stats."""

from __future__ import annotations

import os

from ._common import err, ok, read_db, rows_to_json


def register(mcp) -> None:
    @mcp.tool()
    async def fitness_sync(platform: str = "all") -> dict:
        """Sync fitness data from a platform into the local database.

        Args:
            platform: 'garmin' | 'strava' | 'google_fit' | 'suunto' | 'all' (default).

        Returns records added, time taken, and any errors per platform.
        """
        # Imported lazily so importing the tools package doesn't require
        # provider credentials to be present.
        from sync import run_sync

        try:
            result = await run_sync(platform=platform)
        except Exception as exc:  # noqa: BLE001
            return err(str(exc), platform=platform)
        return ok(result, platform=platform)

    @mcp.tool()
    def fitness_sync_status() -> dict:
        """Last sync datetime, status, and record counts per platform."""
        try:
            with read_db() as db:
                log = rows_to_json(db.query("SELECT * FROM sync_log ORDER BY platform"))
                counts = db.query(
                    """
                    SELECT platform, COUNT(*) AS activities
                    FROM activities GROUP BY platform
                    """
                )
            count_map = {r["platform"]: r["activities"] for r in counts}
            for row in log:
                row["activity_count"] = count_map.get(row["platform"], 0)
            return ok(log, count=len(log))
        except Exception as exc:  # noqa: BLE001
            return err(str(exc))

    @mcp.tool()
    def fitness_get_database_stats() -> dict:
        """Row counts per table, date ranges, and database file size."""
        try:
            tables = ["activities", "sleep", "hrv", "body_metrics"]
            stats = {}
            with read_db() as db:
                for t in tables:
                    rows = db.query(
                        f"SELECT COUNT(*) AS n, MIN(date) AS min_date, MAX(date) AS max_date FROM {t}"
                    )
                    r = rows[0] if rows else {}
                    stats[t] = {
                        "rows": r.get("n", 0),
                        "earliest": r.get("min_date").isoformat() if r.get("min_date") else None,
                        "latest": r.get("max_date").isoformat() if r.get("max_date") else None,
                    }
                db_path = db.path
            size_bytes = os.path.getsize(db_path) if os.path.exists(db_path) else 0
            return ok(
                {"tables": stats, "db_path": db_path, "size_mb": round(size_bytes / 1e6, 2)}
            )
        except Exception as exc:  # noqa: BLE001
            return err(str(exc))
