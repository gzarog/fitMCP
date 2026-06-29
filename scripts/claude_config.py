"""Generate (or install) the Claude Desktop MCP entry for fitness_mcp.

Without ``--write`` it prints a ready-to-paste JSON snippet with absolute paths
filled in. With ``--write`` it merges the ``fitness`` server entry into your
Claude Desktop config, preserving any existing servers and backing up the file
first.

    python scripts/claude_config.py            # print snippet
    python scripts/claude_config.py --write     # install into Claude Desktop
"""

from __future__ import annotations

import argparse
import json
import platform
import shutil
import sys
from pathlib import Path


def default_config_path() -> Path:
    """Where Claude Desktop keeps its config, per OS."""
    system = platform.system()
    if system == "Darwin":
        return Path.home() / "Library/Application Support/Claude/claude_desktop_config.json"
    if system == "Windows":
        import os

        base = Path(os.environ.get("APPDATA", str(Path.home())))
        return base / "Claude/claude_desktop_config.json"
    # Linux / other
    return Path.home() / ".config/Claude/claude_desktop_config.json"


def venv_python(repo_dir: Path) -> Path:
    if platform.system() == "Windows":
        return repo_dir / ".venv/Scripts/python.exe"
    return repo_dir / ".venv/bin/python"


def build_entry(repo_dir: Path) -> dict:
    """The MCP server entry pointing at this repo's venv + server.py."""
    repo = repo_dir.resolve()
    py = venv_python(repo)
    # Prefer the venv python if present; otherwise fall back to plain "python".
    command = str(py) if py.exists() else "python"
    return {
        "command": command,
        "args": [str(repo / "server.py")],
        "env": {"PYTHONPATH": str(repo)},
    }


def merge_config(existing: dict | None, entry: dict, name: str = "fitness") -> dict:
    """Add/replace one server entry without disturbing the rest of the config."""
    cfg = dict(existing) if existing else {}
    servers = dict(cfg.get("mcpServers") or {})
    servers[name] = entry
    cfg["mcpServers"] = servers
    return cfg


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate/install Claude Desktop MCP config.")
    parser.add_argument("--write", action="store_true", help="merge into the Claude Desktop config file")
    parser.add_argument("--repo", default=str(Path(__file__).resolve().parent.parent), help="repo dir")
    parser.add_argument("--path", default=None, help="override config file path")
    parser.add_argument("--name", default="fitness", help="server name (default: fitness)")
    args = parser.parse_args()

    repo_dir = Path(args.repo)
    entry = build_entry(repo_dir)

    if not args.write:
        print(json.dumps({"mcpServers": {args.name: entry}}, indent=2))
        return

    config_path = Path(args.path) if args.path else default_config_path()
    existing = None
    if config_path.exists():
        try:
            existing = json.loads(config_path.read_text())
        except json.JSONDecodeError:
            print(f"Existing config at {config_path} is not valid JSON; aborting.", file=sys.stderr)
            sys.exit(1)
        shutil.copy2(config_path, config_path.with_suffix(config_path.suffix + ".bak"))

    merged = merge_config(existing, entry, args.name)
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(json.dumps(merged, indent=2) + "\n")
    print(f"Installed '{args.name}' MCP server into {config_path}")
    print("Restart Claude Desktop to pick it up.")


if __name__ == "__main__":
    main()
