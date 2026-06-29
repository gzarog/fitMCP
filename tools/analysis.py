"""MCP tools: cross-platform comparison, correlation, trends, raw SQL."""

from __future__ import annotations

import re
from typing import Optional

from ._common import err, ok, read_db, rows_to_json

# metric name -> SQL expression producing one value per date.
# Each entry: (table, value_expr, date_expr). Aggregated per day.
_METRIC_SOURCES = {
    "sleep_score": ("sleep", "AVG(score)", "date"),
    "sleep_duration": ("sleep", "AVG(duration_min)", "date"),
    "hrv": ("hrv", "AVG(rmssd)", "date"),
    "hrv_score": ("hrv", "AVG(hrv_score)", "date"),
    "body_battery": ("hrv", "AVG(body_battery_end)", "date"),
    "training_load": ("activities", "SUM(training_load)", "date"),
    "distance": ("activities", "SUM(distance_m)", "date"),
    "duration": ("activities", "SUM(duration_sec)", "date"),
    "avg_hr": ("activities", "AVG(avg_hr)", "date"),
    "stress": ("body_metrics", "AVG(stress_avg)", "date"),
    "weight": ("body_metrics", "AVG(weight_kg)", "date"),
}

_FORBIDDEN = re.compile(
    r"\b(insert|update|delete|drop|alter|create|attach|detach|copy|pragma|"
    r"replace|truncate|grant|revoke|vacuum|install|load|export)\b",
    re.IGNORECASE,
)


def _daily_series(db, metric: str, date_from: str, date_to: str) -> dict[str, float]:
    table, expr, date_col = _METRIC_SOURCES[metric]
    rows = db.query(
        f"SELECT {date_col} AS d, {expr} AS v FROM {table} "
        f"WHERE {date_col} BETWEEN ? AND ? GROUP BY {date_col} ORDER BY {date_col}",
        [date_from, date_to],
    )
    return {r["d"].isoformat(): r["v"] for r in rows if r["v"] is not None}


def _pearson(xs: list[float], ys: list[float]) -> Optional[float]:
    n = len(xs)
    if n < 2:
        return None
    mean_x = sum(xs) / n
    mean_y = sum(ys) / n
    cov = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
    var_x = sum((x - mean_x) ** 2 for x in xs)
    var_y = sum((y - mean_y) ** 2 for y in ys)
    if var_x == 0 or var_y == 0:
        return None
    return cov / (var_x ** 0.5 * var_y ** 0.5)


def register(mcp) -> None:
    @mcp.tool()
    def fitness_compare_platforms(metric: str, date_from: str, date_to: str) -> dict:
        """Compare a metric across platforms side by side.

        Args:
            metric: 'activities' | 'hr' | 'distance'.
            date_from: YYYY-MM-DD inclusive.
            date_to: YYYY-MM-DD inclusive.
        """
        try:
            metric_exprs = {
                "activities": "COUNT(*)",
                "hr": "ROUND(AVG(avg_hr))",
                "distance": "ROUND(SUM(distance_m))",
            }
            if metric not in metric_exprs:
                return err(f"Unknown metric '{metric}'. Use: {', '.join(metric_exprs)}")
            with read_db() as db:
                rows = rows_to_json(
                    db.query(
                        f"SELECT platform, {metric_exprs[metric]} AS value "
                        "FROM activities WHERE date BETWEEN ? AND ? "
                        "GROUP BY platform ORDER BY platform",
                        [date_from, date_to],
                    )
                )
            return ok(rows, metric=metric, date_range=f"{date_from}..{date_to}")
        except Exception as exc:  # noqa: BLE001
            return err(str(exc))

    @mcp.tool()
    def fitness_correlate(
        metric_a: str, metric_b: str, date_from: str, date_to: str
    ) -> dict:
        """Pearson correlation between two daily metrics, with scatter points.

        Args:
            metric_a: e.g. 'sleep_score' | 'hrv' | 'training_load' | 'body_battery'.
            metric_b: another metric (see same list).
            date_from: YYYY-MM-DD inclusive.
            date_to: YYYY-MM-DD inclusive.
        """
        try:
            for m in (metric_a, metric_b):
                if m not in _METRIC_SOURCES:
                    return err(
                        f"Unknown metric '{m}'. Available: {', '.join(_METRIC_SOURCES)}"
                    )
            with read_db() as db:
                series_a = _daily_series(db, metric_a, date_from, date_to)
                series_b = _daily_series(db, metric_b, date_from, date_to)
            common = sorted(set(series_a) & set(series_b))
            points = [
                {"date": d, metric_a: series_a[d], metric_b: series_b[d]} for d in common
            ]
            xs = [series_a[d] for d in common]
            ys = [series_b[d] for d in common]
            r = _pearson(xs, ys)
            return ok(
                {
                    "correlation": round(r, 4) if r is not None else None,
                    "n": len(common),
                    "points": points,
                },
                metric_a=metric_a,
                metric_b=metric_b,
                date_range=f"{date_from}..{date_to}",
            )
        except Exception as exc:  # noqa: BLE001
            return err(str(exc))

    @mcp.tool()
    def fitness_get_trends(
        metric: str,
        date_from: str,
        date_to: str,
        granularity: str = "week",
    ) -> dict:
        """Time series of a metric aggregated by day/week/month.

        Args:
            metric: any of the correlation metrics (e.g. 'training_load', 'hrv').
            date_from: YYYY-MM-DD inclusive.
            date_to: YYYY-MM-DD inclusive.
            granularity: 'day' | 'week' | 'month' (default 'week').
        """
        try:
            if metric not in _METRIC_SOURCES:
                return err(f"Unknown metric '{metric}'. Available: {', '.join(_METRIC_SOURCES)}")
            if granularity not in ("day", "week", "month"):
                return err("granularity must be 'day', 'week', or 'month'")
            table, expr, date_col = _METRIC_SOURCES[metric]
            bucket = (
                date_col
                if granularity == "day"
                else f"date_trunc('{granularity}', {date_col})"
            )
            with read_db() as db:
                rows = rows_to_json(
                    db.query(
                        f"SELECT {bucket} AS period, {expr} AS value FROM {table} "
                        f"WHERE {date_col} BETWEEN ? AND ? "
                        "GROUP BY period ORDER BY period",
                        [date_from, date_to],
                    )
                )
            return ok(
                rows,
                count=len(rows),
                metric=metric,
                granularity=granularity,
                date_range=f"{date_from}..{date_to}",
            )
        except Exception as exc:  # noqa: BLE001
            return err(str(exc))

    @mcp.tool()
    def fitness_query(sql: str) -> dict:
        """Run a read-only SQL SELECT against the fitness database.

        Only a single SELECT/WITH statement is permitted; any write or DDL
        keyword is rejected and the connection itself is opened read-only.

        Args:
            sql: a DuckDB SELECT query.
        """
        try:
            cleaned = sql.strip().rstrip(";").strip()
            if not cleaned:
                return err("Empty query.")
            if ";" in cleaned:
                return err("Only a single statement is allowed (no ';').")
            lowered = cleaned.lower()
            if not (lowered.startswith("select") or lowered.startswith("with")):
                return err("Only SELECT (or WITH ... SELECT) queries are allowed.")
            if _FORBIDDEN.search(cleaned):
                return err("Query contains a forbidden (non-read-only) keyword.")
            with read_db() as db:
                rows = rows_to_json(db.query(cleaned))
            return ok(rows, count=len(rows))
        except Exception as exc:  # noqa: BLE001
            return err(str(exc))
