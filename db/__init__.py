"""DuckDB persistence layer for fitness_mcp."""

from .database import Database, get_db

__all__ = ["Database", "get_db"]
