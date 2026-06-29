"""Tests for analysis helpers and the read-only SQL guard."""

from __future__ import annotations

from tools.analysis import _pearson

from .conftest import call_tool


def test_pearson_perfect_positive():
    assert abs(_pearson([1, 2, 3], [2, 4, 6]) - 1.0) < 1e-9


def test_pearson_perfect_negative():
    assert abs(_pearson([1, 2, 3], [6, 4, 2]) + 1.0) < 1e-9


def test_pearson_degenerate():
    assert _pearson([1], [1]) is None        # too few points
    assert _pearson([2, 2, 2], [1, 2, 3]) is None  # zero variance


def test_query_allows_select(seeded):
    res = call_tool("fitness_query", {"sql": "SELECT COUNT(*) AS n FROM activities"})
    assert res["success"]
    assert res["data"][0]["n"] >= 1


def test_query_allows_with(seeded):
    res = call_tool(
        "fitness_query",
        {"sql": "WITH x AS (SELECT 1 AS a) SELECT a FROM x"},
    )
    assert res["success"]
    assert res["data"][0]["a"] == 1


def test_query_rejects_writes(seeded):
    for sql in [
        "DELETE FROM activities",
        "UPDATE activities SET title='x'",
        "INSERT INTO activities (id) VALUES ('z')",
        "DROP TABLE activities",
    ]:
        res = call_tool("fitness_query", {"sql": sql})
        assert res["success"] is False


def test_query_rejects_multiple_statements(seeded):
    res = call_tool("fitness_query", {"sql": "SELECT 1; DROP TABLE activities"})
    assert res["success"] is False


def test_query_rejects_disguised_keyword(seeded):
    # A SELECT that smuggles a DDL keyword should be blocked by the guard.
    res = call_tool("fitness_query", {"sql": "SELECT 1 WHERE 1=1 AND copy IS NULL"})
    assert res["success"] is False
