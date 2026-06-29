"""DuckDB connection manager, schema initialization, and upsert helpers.

The whole application persists into a single DuckDB file. Because DuckDB only
allows a single read-write process at a time, ``sync.py`` (writer) and
``server.py`` (mostly reader) are expected to run at different moments. The MCP
sync tool opens a short-lived write connection only while syncing.
"""

from __future__ import annotations

import dataclasses
import json
import os
from datetime import date, datetime
from pathlib import Path
from typing import Any, Iterable, Optional

import duckdb

SCHEMA_PATH = Path(__file__).parent / "schema.sql"

# Map dataclass record type name -> (table, column order). Columns must match
# the dataclass field names exactly (minus raw_json which is JSON-serialized).
_TABLE_COLUMNS = {
    "activities": [
        "id", "platform", "external_id", "date", "start_time", "sport_type",
        "title", "duration_sec", "distance_m", "elevation_gain_m", "avg_hr",
        "max_hr", "calories", "avg_pace_sec_km", "avg_power_w", "training_load",
        "vo2max_estimate", "raw_json",
    ],
    "sleep": [
        "id", "platform", "date", "sleep_start", "sleep_end", "duration_min",
        "score", "deep_min", "rem_min", "light_min", "awake_min", "raw_json",
    ],
    "hrv": [
        "id", "platform", "date", "rmssd", "sdnn", "hrv_score",
        "body_battery_start", "body_battery_end", "raw_json",
    ],
    "body_metrics": [
        "id", "platform", "date", "weight_kg", "bmi", "stress_avg",
        "respiration_avg", "spo2_avg", "raw_json",
    ],
}


def _default_db_path() -> str:
    return os.environ.get("DUCKDB_PATH", "./fitness.duckdb")


class Database:
    """Thin wrapper around a DuckDB connection with fitness-specific helpers."""

    def __init__(self, path: Optional[str] = None, read_only: bool = False):
        self.path = path or _default_db_path()
        self.read_only = read_only
        # DuckDB requires the database directory to exist.
        db_dir = os.path.dirname(os.path.abspath(self.path))
        os.makedirs(db_dir, exist_ok=True)
        self.conn = duckdb.connect(self.path, read_only=read_only)
        if not read_only:
            self.init_schema()

    # -- lifecycle ---------------------------------------------------------
    def init_schema(self) -> None:
        """Create tables and indexes if they do not exist."""
        self.conn.execute(SCHEMA_PATH.read_text())

    def close(self) -> None:
        self.conn.close()

    def __enter__(self) -> "Database":
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()

    # -- writes ------------------------------------------------------------
    def _record_to_id(self, record: Any) -> str:
        return f"{record.platform}:{record.external_id}"

    def _record_row(self, table: str, record: Any) -> list[Any]:
        data = dataclasses.asdict(record)
        # Composite primary key.
        data["id"] = self._record_to_id(record)
        row: list[Any] = []
        for col in _TABLE_COLUMNS[table]:
            if col == "id":
                row.append(data["id"])
                continue
            val = data.get(col)
            if col == "raw_json":
                row.append(json.dumps(val, default=str) if val is not None else None)
            else:
                row.append(val)
        return row

    def upsert(self, table: str, records: Iterable[Any]) -> int:
        """Insert or update records keyed on ``id``. Returns rows written."""
        if table not in _TABLE_COLUMNS:
            raise ValueError(f"Unknown table: {table}")
        records = list(records)
        if not records:
            return 0

        cols = _TABLE_COLUMNS[table]
        placeholders = ", ".join("?" for _ in cols)
        update_cols = [c for c in cols if c != "id"]
        update_clause = ", ".join(f"{c} = excluded.{c}" for c in update_cols)
        sql = (
            f"INSERT INTO {table} ({', '.join(cols)}) VALUES ({placeholders}) "
            f"ON CONFLICT (id) DO UPDATE SET {update_clause}"
        )
        rows = [self._record_row(table, r) for r in records]
        self.conn.executemany(sql, rows)
        return len(rows)

    def upsert_activities(self, records: Iterable[Any]) -> int:
        return self.upsert("activities", records)

    def upsert_sleep(self, records: Iterable[Any]) -> int:
        return self.upsert("sleep", records)

    def upsert_hrv(self, records: Iterable[Any]) -> int:
        return self.upsert("hrv", records)

    def upsert_body_metrics(self, records: Iterable[Any]) -> int:
        return self.upsert("body_metrics", records)

    def record_sync(
        self,
        platform: str,
        records_added: int,
        last_sync_from: Optional[date] = None,
        status: str = "ok",
        error_message: Optional[str] = None,
    ) -> None:
        """Upsert a row in sync_log for the given platform."""
        self.conn.execute(
            """
            INSERT INTO sync_log
                (platform, last_sync_at, last_sync_from, records_added, status, error_message)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT (platform) DO UPDATE SET
                last_sync_at = excluded.last_sync_at,
                last_sync_from = excluded.last_sync_from,
                records_added = excluded.records_added,
                status = excluded.status,
                error_message = excluded.error_message
            """,
            [platform, datetime.now(), last_sync_from, records_added, status, error_message],
        )

    # -- reads -------------------------------------------------------------
    def query(self, sql: str, params: Optional[list[Any]] = None) -> list[dict[str, Any]]:
        """Run a query and return rows as a list of dicts."""
        cur = self.conn.execute(sql, params or [])
        columns = [d[0] for d in cur.description] if cur.description else []
        return [dict(zip(columns, row)) for row in cur.fetchall()]


def get_db(read_only: bool = False, path: Optional[str] = None) -> Database:
    """Convenience factory used by tools and the CLI."""
    return Database(path=path, read_only=read_only)
