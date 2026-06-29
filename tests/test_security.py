"""Tests for filesystem hardening of secrets and token caches."""

from __future__ import annotations

import os
import stat

import pytest

import security

pytestmark = pytest.mark.skipif(os.name != "posix", reason="POSIX permission bits")


def _mode(path) -> int:
    return stat.S_IMODE(os.stat(path).st_mode)


def test_harden_file(tmp_path):
    f = tmp_path / ".env"
    f.write_text("SECRET=1")
    os.chmod(f, 0o644)
    security.harden_file(f)
    assert _mode(f) == 0o600


def test_harden_dir_recurses(tmp_path):
    d = tmp_path / "garth"
    sub = d / "oauth"
    sub.mkdir(parents=True)
    token = sub / "token.json"
    token.write_text("{}")
    os.chmod(d, 0o755)
    os.chmod(token, 0o644)
    security.harden_dir(d)
    assert _mode(d) == 0o700
    assert _mode(sub) == 0o700
    assert _mode(token) == 0o600


def test_world_accessible_detection(tmp_path):
    f = tmp_path / "secret"
    f.write_text("x")
    os.chmod(f, 0o600)
    assert security.is_world_or_group_accessible(f) is False
    os.chmod(f, 0o644)
    assert security.is_world_or_group_accessible(f) is True


def test_warn_if_exposed_prints(tmp_path, capsys):
    f = tmp_path / ".env"
    f.write_text("x")
    os.chmod(f, 0o644)
    security.warn_if_exposed(str(f))
    assert "readable by other users" in capsys.readouterr().err
    os.chmod(f, 0o600)
    security.warn_if_exposed(str(f))
    assert capsys.readouterr().err == ""


def test_missing_path_is_safe(tmp_path):
    missing = tmp_path / "nope"
    security.harden_file(missing)  # no raise
    security.harden_dir(missing)
    assert security.is_world_or_group_accessible(missing) is False
    security.warn_if_exposed("")  # empty path ignored
