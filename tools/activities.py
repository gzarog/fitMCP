"""MCP tools: activities / workouts."""

from __future__ import annotations

from ._common import err, ok, platform_filter, read_db, rows_to_json


def register(mcp) -> None:
    @mcp.tool()
    def fitness_get_activities(
        date_from: str,
        date_to: str,
        platform: str = "all",
        sport_type: str = "all",
        limit: int = 50,
        offset: int = 0,
    ) -> dict:
        """List activities in a date range with optional filters and pagination.

        Args:
            date_from: start date YYYY-MM-DD (inclusive).
            date_to: end date YYYY-MM-DD (inclusive).
            platform: 'all' | 'garmin' | 'strava'.
            sport_type: 'all' | 'running' | 'cycling' | 'crossfit' | ...
            limit: max rows (default 50).
            offset: rows to skip for pagination (default 0).
        """
        try:
            sql = (
                "SELECT id, platform, external_id, date, start_time, sport_type, "
                "title, duration_sec, distance_m, elevation_gain_m, avg_hr, max_hr, "
                "calories, avg_pace_sec_km, avg_power_w, training_load, vo2max_estimate "
                "FROM activities WHERE date BETWEEN ? AND ?"
            )
            params: list = [date_from, date_to]
            pf, pp = platform_filter(platform)
            sql += pf
            params += pp
            if sport_type and sport_type != "all":
                sql += " AND sport_type = ?"
                params.append(sport_type)
            sql += " ORDER BY date DESC, start_time DESC LIMIT ? OFFSET ?"
            params += [limit, offset]

            with read_db() as db:
                rows = rows_to_json(db.query(sql, params))
                total = db.query(
                    "SELECT COUNT(*) AS n FROM activities WHERE date BETWEEN ? AND ?" + pf,
                    [date_from, date_to] + pp,
                )[0]["n"]
            return ok(
                rows,
                count=len(rows),
                total=total,
                limit=limit,
                offset=offset,
                platform=platform,
                date_range=f"{date_from}..{date_to}",
            )
        except Exception as exc:  # noqa: BLE001
            return err(str(exc))

    @mcp.tool()
    def fitness_get_activity_detail(activity_id: str) -> dict:
        """Full detail for one activity, including the raw provider payload.

        Args:
            activity_id: composite id 'platform:external_id', e.g. 'garmin:12345'.
        """
        try:
            with read_db() as db:
                rows = rows_to_json(
                    db.query("SELECT * FROM activities WHERE id = ?", [activity_id])
                )
            if not rows:
                return err(f"No activity found with id '{activity_id}'", activity_id=activity_id)
            return ok(rows[0], activity_id=activity_id)
        except Exception as exc:  # noqa: BLE001
            return err(str(exc))

    @mcp.tool()
    def fitness_get_personal_bests(sport_type: str) -> dict:
        """Best distance, fastest pace, highest HR, and most elevation for a sport.

        Args:
            sport_type: 'running' | 'cycling' | ...
        """
        try:
            with read_db() as db:
                longest = db.query(
                    "SELECT id, date, distance_m, title FROM activities "
                    "WHERE sport_type = ? AND distance_m IS NOT NULL "
                    "ORDER BY distance_m DESC LIMIT 1",
                    [sport_type],
                )
                fastest = db.query(
                    "SELECT id, date, avg_pace_sec_km, title FROM activities "
                    "WHERE sport_type = ? AND avg_pace_sec_km IS NOT NULL AND distance_m >= 1000 "
                    "ORDER BY avg_pace_sec_km ASC LIMIT 1",
                    [sport_type],
                )
                max_hr = db.query(
                    "SELECT id, date, max_hr, title FROM activities "
                    "WHERE sport_type = ? AND max_hr IS NOT NULL "
                    "ORDER BY max_hr DESC LIMIT 1",
                    [sport_type],
                )
                most_elev = db.query(
                    "SELECT id, date, elevation_gain_m, title FROM activities "
                    "WHERE sport_type = ? AND elevation_gain_m IS NOT NULL "
                    "ORDER BY elevation_gain_m DESC LIMIT 1",
                    [sport_type],
                )
            data = {
                "longest_distance": rows_to_json(longest)[0] if longest else None,
                "fastest_pace": rows_to_json(fastest)[0] if fastest else None,
                "highest_max_hr": rows_to_json(max_hr)[0] if max_hr else None,
                "most_elevation": rows_to_json(most_elev)[0] if most_elev else None,
            }
            return ok(data, sport_type=sport_type)
        except Exception as exc:  # noqa: BLE001
            return err(str(exc))
