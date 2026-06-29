"""MCP tools: sleep, HRV, body battery, recovery status."""

from __future__ import annotations

from ._common import err, ok, parse_date, platform_filter, read_db, rows_to_json


def register(mcp) -> None:
    @mcp.tool()
    def fitness_get_sleep(date_from: str, date_to: str, platform: str = "all") -> dict:
        """Sleep records in a date range (duration, score, stages).

        Args:
            date_from: YYYY-MM-DD inclusive.
            date_to: YYYY-MM-DD inclusive.
            platform: 'all' | 'garmin' | ...
        """
        try:
            sql = "SELECT * FROM sleep WHERE date BETWEEN ? AND ?"
            params: list = [date_from, date_to]
            pf, pp = platform_filter(platform)
            sql += pf + " ORDER BY date DESC"
            params += pp
            with read_db() as db:
                rows = rows_to_json(db.query(sql, params))
            return ok(rows, count=len(rows), platform=platform, date_range=f"{date_from}..{date_to}")
        except Exception as exc:  # noqa: BLE001
            return err(str(exc))

    @mcp.tool()
    def fitness_get_hrv(date_from: str, date_to: str, platform: str = "all") -> dict:
        """HRV records in a date range, including body battery start/end.

        Args:
            date_from: YYYY-MM-DD inclusive.
            date_to: YYYY-MM-DD inclusive.
            platform: 'all' | 'garmin' | ...
        """
        try:
            sql = "SELECT * FROM hrv WHERE date BETWEEN ? AND ?"
            params: list = [date_from, date_to]
            pf, pp = platform_filter(platform)
            sql += pf + " ORDER BY date DESC"
            params += pp
            with read_db() as db:
                rows = rows_to_json(db.query(sql, params))
            return ok(rows, count=len(rows), platform=platform, date_range=f"{date_from}..{date_to}")
        except Exception as exc:  # noqa: BLE001
            return err(str(exc))

    @mcp.tool()
    def fitness_get_body_battery(date_from: str, date_to: str) -> dict:
        """Body battery trend (Garmin): start and end levels per day.

        Args:
            date_from: YYYY-MM-DD inclusive.
            date_to: YYYY-MM-DD inclusive.
        """
        try:
            with read_db() as db:
                rows = rows_to_json(
                    db.query(
                        "SELECT date, body_battery_start, body_battery_end "
                        "FROM hrv WHERE date BETWEEN ? AND ? "
                        "AND (body_battery_start IS NOT NULL OR body_battery_end IS NOT NULL) "
                        "ORDER BY date DESC",
                        [date_from, date_to],
                    )
                )
            return ok(rows, count=len(rows), date_range=f"{date_from}..{date_to}")
        except Exception as exc:  # noqa: BLE001
            return err(str(exc))

    @mcp.tool()
    def fitness_get_recovery_status(date: str = "today") -> dict:
        """Single-day recovery snapshot: HRV, sleep score, body battery, stress.

        Args:
            date: YYYY-MM-DD, or 'today' / 'yesterday' (default 'today').
        """
        try:
            day = parse_date(date).isoformat()
            with read_db() as db:
                hrv = rows_to_json(
                    db.query(
                        "SELECT rmssd, hrv_score, body_battery_start, body_battery_end "
                        "FROM hrv WHERE date = ? LIMIT 1",
                        [day],
                    )
                )
                sleep = rows_to_json(
                    db.query(
                        "SELECT score AS sleep_score, duration_min FROM sleep WHERE date = ? LIMIT 1",
                        [day],
                    )
                )
                body = rows_to_json(
                    db.query(
                        "SELECT stress_avg, weight_kg FROM body_metrics WHERE date = ? LIMIT 1",
                        [day],
                    )
                )
            snapshot = {
                "date": day,
                "hrv": hrv[0] if hrv else None,
                "sleep": sleep[0] if sleep else None,
                "body": body[0] if body else None,
            }
            return ok(snapshot, date=day)
        except Exception as exc:  # noqa: BLE001
            return err(str(exc))
