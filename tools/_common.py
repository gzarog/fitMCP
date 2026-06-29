"""Shared helpers for MCP tools: response envelope, DB access, serialization."""

from __future__ import annotations

import json
from contextlib import contextmanager
from datetime import date, datetime, timedelta
from typing import Any, Optional

from db.database import Database


def ok(data: Any, **meta: Any) -> dict:
    return {"success": True, "data": data, "error": None, "meta": meta}


def err(message: str, **meta: Any) -> dict:
    return {"success": False, "data": None, "error": message, "meta": meta}


@contextmanager
def read_db():
    """Open a short-lived read-only connection."""
    db = Database(read_only=True)
    try:
        yield db
    finally:
        db.close()


def jsonable(value: Any) -> Any:
    """Make DuckDB values JSON-serializable (dates, datetimes, embedded JSON)."""
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, dict):
        return {k: jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [jsonable(v) for v in value]
    return value


def rows_to_json(rows: list[dict]) -> list[dict]:
    out = []
    for row in rows:
        clean = {}
        for k, v in row.items():
            if k == "raw_json" and isinstance(v, str):
                try:
                    clean[k] = json.loads(v)
                    continue
                except (json.JSONDecodeError, TypeError):
                    pass
            clean[k] = jsonable(v)
        out.append(clean)
    return out


def parse_date(value: str, *, default: Optional[date] = None) -> date:
    """Parse YYYY-MM-DD, also accepting 'today'/'yesterday'."""
    if value in (None, "", "today"):
        return default if value in (None, "") and default else date.today()
    if value == "yesterday":
        return date.today() - timedelta(days=1)
    return datetime.strptime(value, "%Y-%m-%d").date()


def platform_filter(platform: str, column: str = "platform") -> tuple[str, list]:
    """Return a SQL fragment + params to filter by platform ('all' = no filter)."""
    if platform and platform != "all":
        return f" AND {column} = ?", [platform]
    return "", []
