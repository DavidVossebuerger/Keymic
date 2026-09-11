"""Tests for cmd_stop, cmd_status, _state_dir helpers."""
import os
import subprocess
import sys
from pathlib import Path
import pytest


def test_state_dir_uses_home(tmp_path, monkeypatch):
    """State dir is HOME-relative for sandbox-friendliness."""
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("XDG_RUNTIME_DIR", raising=False)
    from keymic.__main__ import _state_dir
    d = _state_dir()
    assert d == tmp_path / ".local" / "share" / "keymic"
    assert d.exists()


def test_state_dir_ignores_xdg_runtime_dir(tmp_path, monkeypatch):
    """XDG_RUNTIME_DIR is intentionally NOT used — pw-cat needs the real one."""
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("XDG_RUNTIME_DIR", "/some/other/path")
    from keymic.__main__ import _state_dir
    d = _state_dir()
    assert d == tmp_path / ".local" / "share" / "keymic"
    assert "/some/other/path" not in str(d)


def test_cmd_status_no_pid_file(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("XDG_RUNTIME_DIR", raising=False)
    from keymic.__main__ import cmd_status
    rc = cmd_status(None)
    assert rc == 1
    out = capsys.readouterr().out
    assert "läuft nicht" in out


def test_cmd_status_alive(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("XDG_RUNTIME_DIR", raising=False)
    state = tmp_path / ".local" / "share" / "keymic"
    state.mkdir(parents=True, exist_ok=True)
    # Use the test process's own PID — definitely alive
    state.joinpath("keymic.pid").write_text(str(os.getpid()))
    state.joinpath("keymic.log").write_text("log content")

    from keymic.__main__ import cmd_status
    rc = cmd_status(None)
    assert rc == 0
    out = capsys.readouterr().out
    assert "läuft" in out
    assert str(os.getpid()) in out


def test_cmd_status_stale_pid(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("XDG_RUNTIME_DIR", raising=False)
    state = tmp_path / ".local" / "share" / "keymic"
    state.mkdir(parents=True, exist_ok=True)
    # 999999 is extremely unlikely to be a real PID
    state.joinpath("keymic.pid").write_text("999999")

    from keymic.__main__ import cmd_status
    rc = cmd_status(None)
    assert rc == 1
    out = capsys.readouterr().out
    assert "veraltete" in out
    assert not state.joinpath("keymic.pid").exists()


def test_cmd_stop_no_pid_file(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("XDG_RUNTIME_DIR", raising=False)
    from keymic.__main__ import cmd_stop
    rc = cmd_stop(None)
    assert rc == 1


def test_cmd_stop_invalid_pid(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("XDG_RUNTIME_DIR", raising=False)
    state = tmp_path / ".local" / "share" / "keymic"
    state.mkdir(parents=True, exist_ok=True)
    state.joinpath("keymic.pid").write_text("not-a-number")

    from keymic.__main__ import cmd_stop
    rc = cmd_stop(None)
    assert rc == 1
    assert not state.joinpath("keymic.pid").exists()


def test_cmd_stop_already_dead(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("XDG_RUNTIME_DIR", raising=False)
    state = tmp_path / ".local" / "share" / "keymic"
    state.mkdir(parents=True, exist_ok=True)
    state.joinpath("keymic.pid").write_text("999999")

    from keymic.__main__ import cmd_stop
    rc = cmd_stop(None)
    assert rc == 1
    assert not state.joinpath("keymic.pid").exists()
