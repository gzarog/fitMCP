# Convenience targets for fitness_mcp. Run `make help` for the list.

PY := .venv/bin/python
PIP := .venv/bin/pip

.PHONY: help setup dev login sync sync-full serve test claude-config claude-install clean

help:
	@echo "fitness_mcp make targets:"
	@echo "  make setup          Create venv, install deps, scaffold .env"
	@echo "  make dev            Setup with dev deps + run tests"
	@echo "  make login          Interactive Garmin login (password not stored)"
	@echo "  make sync           Sync all platforms (last 30 days)"
	@echo "  make sync-full      Sync all platforms (full history)"
	@echo "  make serve          Run the MCP server (stdio)"
	@echo "  make test           Run the test suite"
	@echo "  make claude-config  Print the Claude Desktop config snippet"
	@echo "  make claude-install Install the entry into Claude Desktop config"
	@echo "  make clean          Remove venv and Python caches"

setup:
	./setup.sh

dev:
	./setup.sh --dev

login:
	$(PY) login.py

sync:
	$(PY) sync.py --platform all

sync-full:
	$(PY) sync.py --platform all --full-history

serve:
	$(PY) server.py

test:
	PYTHONPATH=. $(PY) -m pytest

claude-config:
	$(PY) scripts/claude_config.py

claude-install:
	$(PY) scripts/claude_config.py --write

clean:
	rm -rf .venv .pytest_cache
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
