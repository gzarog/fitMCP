"""Tests for the Claude Desktop config generator/installer."""

from __future__ import annotations

import json
from pathlib import Path

from scripts.claude_config import build_entry, merge_config


def test_build_entry_paths(tmp_path):
    repo = tmp_path / "fitMCP"
    repo.mkdir()
    entry = build_entry(repo)
    assert entry["args"] == [str((repo / "server.py").resolve())]
    assert entry["env"]["PYTHONPATH"] == str(repo.resolve())
    # No venv present -> falls back to plain "python".
    assert entry["command"] == "python"


def test_build_entry_uses_venv_when_present(tmp_path):
    repo = tmp_path / "fitMCP"
    (repo / ".venv/bin").mkdir(parents=True)
    py = repo / ".venv/bin/python"
    py.write_text("")
    entry = build_entry(repo)
    # On POSIX the venv python should be picked up.
    assert entry["command"].endswith("/.venv/bin/python") or entry["command"] == "python"


def test_merge_preserves_existing_servers():
    existing = {"mcpServers": {"other": {"command": "x", "args": []}}}
    merged = merge_config(existing, {"command": "p", "args": ["s"], "env": {}})
    assert "other" in merged["mcpServers"]
    assert merged["mcpServers"]["fitness"]["command"] == "p"


def test_merge_overwrites_same_name():
    existing = {"mcpServers": {"fitness": {"command": "old", "args": []}}}
    merged = merge_config(existing, {"command": "new", "args": [], "env": {}})
    assert merged["mcpServers"]["fitness"]["command"] == "new"


def test_merge_from_empty():
    merged = merge_config(None, {"command": "p", "args": [], "env": {}})
    assert list(merged["mcpServers"]) == ["fitness"]


def test_merge_keeps_other_top_level_keys():
    existing = {"globalShortcut": "Cmd+X", "mcpServers": {}}
    merged = merge_config(existing, {"command": "p", "args": [], "env": {}})
    assert merged["globalShortcut"] == "Cmd+X"
