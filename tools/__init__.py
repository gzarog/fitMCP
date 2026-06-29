"""MCP tool modules. Each exposes ``register(mcp)`` to attach its tools."""

from . import activities, analysis, health, sync_tools, training

__all__ = ["activities", "analysis", "health", "sync_tools", "training"]


def register_all(mcp) -> None:
    """Register every tool group on the given FastMCP instance."""
    sync_tools.register(mcp)
    activities.register(mcp)
    health.register(mcp)
    training.register(mcp)
    analysis.register(mcp)
