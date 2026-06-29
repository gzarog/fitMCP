"""Filesystem hardening helpers for secrets and cached session tokens.

Keeps credentials readable only by the current user and warns when a secrets
file (like ``.env``) is exposed to other accounts on the machine. POSIX-only
permission bits are applied; on Windows these calls are no-ops with a note.
"""

from __future__ import annotations

import os
import stat
import sys
from pathlib import Path

_POSIX = os.name == "posix"


def harden_file(path: str | os.PathLike, mode: int = 0o600) -> None:
    """Restrict a file to owner read/write (0600 by default)."""
    if not _POSIX:
        return
    p = Path(path)
    if p.exists():
        os.chmod(p, mode)


def harden_dir(path: str | os.PathLike, dir_mode: int = 0o700, file_mode: int = 0o600) -> None:
    """Restrict a directory (0700) and every file inside it (0600).

    Used for the garth token cache (``GARTH_HOME``), which holds session tokens
    equivalent to a logged-in browser.
    """
    if not _POSIX:
        return
    root = Path(path)
    if not root.exists():
        return
    os.chmod(root, dir_mode)
    for child in root.rglob("*"):
        if child.is_dir():
            os.chmod(child, dir_mode)
        else:
            os.chmod(child, file_mode)


def is_world_or_group_accessible(path: str | os.PathLike) -> bool:
    """True if group/other have any permission bits on the file."""
    if not _POSIX:
        return False
    p = Path(path)
    if not p.exists():
        return False
    mode = p.stat().st_mode
    return bool(mode & (stat.S_IRWXG | stat.S_IRWXO))


def warn_if_exposed(path: str | os.PathLike) -> None:
    """Print a stderr warning (and suggested fix) if a secrets file is exposed."""
    if not path or not _POSIX:
        return
    if is_world_or_group_accessible(path):
        print(
            f"[security] Warning: {path} is readable by other users. "
            f"Run: chmod 600 {path}",
            file=sys.stderr,
        )
