"""Interactive Garmin login — bootstraps a cached session token.

Run this once so you never have to store your Garmin password on disk::

    python login.py

You'll be prompted for your email/password (and an MFA code if enabled). The
password is read with getpass (not echoed, not saved); only the resulting
session token is written to GARTH_HOME, with owner-only permissions. After this,
``sync.py`` and the MCP server reuse the cached token and you can leave
GARMIN_PASSWORD out of your .env entirely.
"""

from __future__ import annotations

import sys

from dotenv import load_dotenv

from providers.garmin import GarminProvider

load_dotenv()


def main() -> None:
    provider = GarminProvider()
    try:
        name = provider.login_interactive()
    except Exception as exc:  # noqa: BLE001
        print(f"Login failed: {exc}", file=sys.stderr)
        sys.exit(1)
    print(f"Logged in as {name}. Session token cached at {provider.garth_home} (owner-only).")
    print("You can now remove GARMIN_PASSWORD from .env if you set it.")


if __name__ == "__main__":
    main()
