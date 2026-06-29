"""fitness_mcp — MCP server entry point.

Runs over stdio so it works with Claude Desktop, Cursor, Windsurf, VS Code, and
any other MCP client. Start with::

    python server.py
"""

from __future__ import annotations

from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

from tools import register_all

load_dotenv()

mcp = FastMCP("fitness")
register_all(mcp)


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
