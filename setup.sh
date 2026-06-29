#!/usr/bin/env bash
#
# One-command setup for fitness_mcp (macOS / Linux).
#
#   ./setup.sh                 # venv + deps + .env, then print next steps
#   ./setup.sh --dev           # also install dev deps and run the test suite
#   ./setup.sh --login         # also run interactive Garmin login
#   ./setup.sh --sync          # also run an initial sync (implies a token exists)
#   ./setup.sh --full-history  # with --sync, pull full history instead of 30 days
#   ./setup.sh --claude        # also install the Claude Desktop MCP config
#
# Flags combine, e.g.:  ./setup.sh --dev --login --sync --claude
set -euo pipefail

cd "$(dirname "$0")"

DEV=0; DO_LOGIN=0; DO_SYNC=0; FULL_HISTORY=0; DO_CLAUDE=0
for arg in "$@"; do
  case "$arg" in
    --dev) DEV=1 ;;
    --login) DO_LOGIN=1 ;;
    --sync) DO_SYNC=1 ;;
    --full-history) FULL_HISTORY=1 ;;
    --claude) DO_CLAUDE=1 ;;
    -h|--help) grep '^#' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "Unknown flag: $arg" >&2; exit 1 ;;
  esac
done

say() { printf '\n\033[1m==> %s\033[0m\n' "$1"; }

# 1. Find a suitable Python (>= 3.11).
say "Checking Python"
PYBIN=""
for cand in python3.13 python3.12 python3.11 python3 python; do
  if command -v "$cand" >/dev/null 2>&1; then
    ver="$("$cand" -c 'import sys; print("%d.%d" % sys.version_info[:2])' 2>/dev/null || echo 0.0)"
    major="${ver%%.*}"; minor="${ver##*.}"
    if [ "$major" -gt 3 ] || { [ "$major" -eq 3 ] && [ "$minor" -ge 11 ]; }; then
      PYBIN="$cand"; break
    fi
  fi
done
if [ -z "$PYBIN" ]; then
  echo "Python 3.11+ not found. Please install it and re-run." >&2
  exit 1
fi
echo "Using $PYBIN ($("$PYBIN" --version 2>&1))"

# 2. Virtual environment.
if [ ! -d .venv ]; then
  say "Creating virtual environment (.venv)"
  "$PYBIN" -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate
python -m pip install --quiet --upgrade pip

# 3. Dependencies.
say "Installing dependencies"
if [ "$DEV" -eq 1 ]; then
  pip install --quiet -r requirements-dev.txt
else
  pip install --quiet -r requirements.txt
fi

# 4. .env scaffold + lock-down.
if [ ! -f .env ]; then
  say "Creating .env from template"
  cp .env.example .env
  echo "Edit .env to add your credentials (Garmin email; OAuth tokens as needed)."
fi
chmod 600 .env 2>/dev/null || true

# 5. Optional: dev tests.
if [ "$DEV" -eq 1 ]; then
  say "Running test suite"
  PYTHONPATH=. pytest
fi

# 6. Optional: Garmin interactive login.
if [ "$DO_LOGIN" -eq 1 ]; then
  say "Garmin login (password is not stored)"
  python login.py
fi

# 7. Optional: initial sync.
if [ "$DO_SYNC" -eq 1 ]; then
  say "Initial sync"
  if [ "$FULL_HISTORY" -eq 1 ]; then
    python sync.py --platform all --full-history
  else
    python sync.py --platform all
  fi
fi

# 8. Optional: install Claude Desktop config.
if [ "$DO_CLAUDE" -eq 1 ]; then
  say "Installing Claude Desktop MCP config"
  python scripts/claude_config.py --write
fi

say "Setup complete"
cat <<EOF
Next steps:
  1. Edit .env with your credentials (if you haven't).
  2. Garmin login (once):     python login.py
  3. Pull data:               python sync.py --platform garmin --full-history
  4. Add to Claude Desktop:   python scripts/claude_config.py --write
                              (or print the snippet: python scripts/claude_config.py)
  5. Restart Claude Desktop and ask away.

Tip: re-run anytime with  ./setup.sh --dev  to install dev deps and run tests.
EOF
