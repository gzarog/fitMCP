"""Sync runner for schedulers (Windows Task Scheduler / cron / launchd).

Runs a sync and appends a one-line, timestamped summary to ``logs/sync.log`` so
unattended runs leave an audit trail. Exits non-zero if any platform errored, so
the scheduler surfaces failures.

    python scripts/scheduled_sync.py --platform all
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import datetime
from pathlib import Path

# Make the repo root importable when run directly by a scheduler.
_REPO = Path(__file__).resolve().parent.parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from dotenv import load_dotenv  # noqa: E402

from sync import run_sync  # noqa: E402

load_dotenv()


def format_log_line(result: dict, when: datetime | None = None) -> str:
    """Render a sync result dict as a compact single log line."""
    when = when or datetime.now()
    platforms = result.get("platforms", [])
    per = ",".join(f"{p['platform']}={p['records_added']}" for p in platforms)
    errs = sum(len(p.get("errors", [])) for p in platforms)
    return (
        f"{when.isoformat(timespec='seconds')} "
        f"total={result.get('total_records', 0)} "
        f"deduped={result.get('deduped', 0)} "
        f"[{per}] errors={errs} elapsed={result.get('elapsed_sec', '?')}s"
    )


def count_errors(result: dict) -> int:
    return sum(len(p.get("errors", [])) for p in result.get("platforms", []))


def _append(log_file: Path, line: str) -> None:
    log_file.parent.mkdir(parents=True, exist_ok=True)
    with log_file.open("a", encoding="utf-8") as fh:
        fh.write(line + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Scheduled sync runner with logging.")
    parser.add_argument("--platform", default="all", help="garmin|strava|google_fit|suunto|all")
    parser.add_argument("--full-history", action="store_true")
    parser.add_argument("--log-dir", default=str(_REPO / "logs"))
    args = parser.parse_args()

    log_file = Path(args.log_dir) / "sync.log"
    try:
        result = asyncio.run(
            run_sync(platform=args.platform, full_history=args.full_history)
        )
    except Exception as exc:  # noqa: BLE001
        line = f"{datetime.now().isoformat(timespec='seconds')} FAILED {exc}"
        _append(log_file, line)
        print(line, file=sys.stderr)
        sys.exit(1)

    line = format_log_line(result)
    _append(log_file, line)
    print(line)
    sys.exit(1 if count_errors(result) else 0)


if __name__ == "__main__":
    main()
