"""MCP tools: training load, VO2max trend, weekly summary, sport breakdown."""

from __future__ import annotations

from datetime import date, timedelta

from ._common import err, ok, platform_filter, read_db, rows_to_json


def register(mcp) -> None:
    @mcp.tool()
    def fitness_get_training_load(weeks: int = 4, platform: str = "all") -> dict:
        """Weekly training-load trend over the last N weeks.

        Args:
            weeks: number of weeks to include (default 4).
            platform: 'all' | 'garmin' | 'strava'.
        """
        try:
            start = (date.today() - timedelta(weeks=weeks)).isoformat()
            sql = (
                "SELECT date_trunc('week', date) AS week, "
                "COUNT(*) AS activities, "
                "COALESCE(SUM(training_load), 0) AS total_load, "
                "COALESCE(SUM(duration_sec), 0) AS total_duration_sec "
                "FROM activities WHERE date >= ?"
            )
            params: list = [start]
            pf, pp = platform_filter(platform)
            sql += pf + " GROUP BY week ORDER BY week DESC"
            params += pp
            with read_db() as db:
                rows = rows_to_json(db.query(sql, params))
            return ok(rows, count=len(rows), weeks=weeks, platform=platform)
        except Exception as exc:  # noqa: BLE001
            return err(str(exc))

    @mcp.tool()
    def fitness_get_vo2max_trend(months: int = 6) -> dict:
        """VO2max estimates over time (latest estimate per week).

        Args:
            months: how many months back to include (default 6).
        """
        try:
            start = (date.today() - timedelta(days=months * 31)).isoformat()
            with read_db() as db:
                rows = rows_to_json(
                    db.query(
                        "SELECT date, vo2max_estimate, sport_type FROM activities "
                        "WHERE vo2max_estimate IS NOT NULL AND date >= ? "
                        "ORDER BY date DESC",
                        [start],
                    )
                )
            return ok(rows, count=len(rows), months=months)
        except Exception as exc:  # noqa: BLE001
            return err(str(exc))

    @mcp.tool()
    def fitness_get_weekly_summary(week_offset: int = 0) -> dict:
        """Activity totals for a week (count, time, distance, load).

        Args:
            week_offset: 0 = current week, -1 = last week, etc.
        """
        try:
            today = date.today()
            monday = today - timedelta(days=today.weekday())
            week_start = monday + timedelta(weeks=week_offset)
            week_end = week_start + timedelta(days=6)
            with read_db() as db:
                totals = db.query(
                    "SELECT COUNT(*) AS activities, "
                    "COALESCE(SUM(duration_sec), 0) AS total_duration_sec, "
                    "COALESCE(SUM(distance_m), 0) AS total_distance_m, "
                    "COALESCE(SUM(training_load), 0) AS total_load, "
                    "COALESCE(SUM(elevation_gain_m), 0) AS total_elevation_m "
                    "FROM activities WHERE date BETWEEN ? AND ?",
                    [week_start.isoformat(), week_end.isoformat()],
                )
                by_sport = rows_to_json(
                    db.query(
                        "SELECT sport_type, COUNT(*) AS count, "
                        "COALESCE(SUM(duration_sec), 0) AS duration_sec "
                        "FROM activities WHERE date BETWEEN ? AND ? "
                        "GROUP BY sport_type ORDER BY duration_sec DESC",
                        [week_start.isoformat(), week_end.isoformat()],
                    )
                )
            summary = rows_to_json(totals)[0] if totals else {}
            summary["by_sport"] = by_sport
            return ok(
                summary,
                week_start=week_start.isoformat(),
                week_end=week_end.isoformat(),
                week_offset=week_offset,
            )
        except Exception as exc:  # noqa: BLE001
            return err(str(exc))

    @mcp.tool()
    def fitness_get_sport_breakdown(date_from: str, date_to: str) -> dict:
        """Time / distance / count per sport type in a date range.

        Args:
            date_from: YYYY-MM-DD inclusive.
            date_to: YYYY-MM-DD inclusive.
        """
        try:
            with read_db() as db:
                rows = rows_to_json(
                    db.query(
                        "SELECT sport_type, COUNT(*) AS count, "
                        "COALESCE(SUM(duration_sec), 0) AS total_duration_sec, "
                        "COALESCE(SUM(distance_m), 0) AS total_distance_m, "
                        "ROUND(AVG(avg_hr)) AS avg_hr "
                        "FROM activities WHERE date BETWEEN ? AND ? "
                        "GROUP BY sport_type ORDER BY total_duration_sec DESC",
                        [date_from, date_to],
                    )
                )
            return ok(rows, count=len(rows), date_range=f"{date_from}..{date_to}")
        except Exception as exc:  # noqa: BLE001
            return err(str(exc))
