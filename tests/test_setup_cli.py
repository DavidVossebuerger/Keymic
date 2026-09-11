from pathlib import Path
from unittest.mock import patch
import pytest
from keymic.setup_cli import run_setup


def test_run_setup_creates_config(tmp_path, monkeypatch):
    inputs = iter(["test-groq-key", "3"])  # API key, install mode = skip
    monkeypatch.setattr("builtins.input", lambda _: next(inputs))
    monkeypatch.setattr("keymic.setup_cli._validate_groq_key", lambda k: True)
    monkeypatch.setattr("keymic.setup_cli._select_hotkey", lambda: "KEY_F12")
    monkeypatch.setattr("keymic.setup_cli._select_injection", lambda: "auto")
    monkeypatch.setattr("keymic.setup_cli._select_language", lambda: "de")
    monkeypatch.setattr("keymic.setup_cli._ask_vocab", lambda: [])

    config_path = tmp_path / "config.toml"
    rc = run_setup(config_path=config_path)
    assert rc == 0
    assert config_path.exists()
    content = config_path.read_text()
    assert "KEY_F12" in content
    assert "test-groq-key" not in content  # never written literally


def test_run_setup_invalid_key_exits(tmp_path, monkeypatch):
    monkeypatch.setattr("builtins.input", lambda _: "bad-key")
    monkeypatch.setattr("keymic.setup_cli._validate_groq_key", lambda k: False)

    config_path = tmp_path / "config.toml"
    rc = run_setup(config_path=config_path)
    assert rc != 0
    assert not config_path.exists()


def test_run_setup_with_vocab(tmp_path, monkeypatch):
    inputs = iter(["my-key", "3"])  # API key, install mode = skip
    monkeypatch.setattr("builtins.input", lambda _: next(inputs))
    monkeypatch.setattr("keymic.setup_cli._validate_groq_key", lambda k: True)
    monkeypatch.setattr("keymic.setup_cli._select_hotkey", lambda: "KEY_RIGHTCTRL")
    monkeypatch.setattr("keymic.setup_cli._select_injection", lambda: "ydotool")
    monkeypatch.setattr("keymic.setup_cli._select_language", lambda: "en")
    monkeypatch.setattr("keymic.setup_cli._ask_vocab", lambda: ["Foo", "Bar"])

    config_path = tmp_path / "config.toml"
    rc = run_setup(config_path=config_path)
    assert rc == 0
    content = config_path.read_text()
    assert "Foo" in content
    assert "Bar" in content
    assert "ydotool" not in content or "method" in content  # method stored, not the literal name in vocab


def test_run_setup_aborts_on_existing_config(tmp_path, monkeypatch):
    config_path = tmp_path / "config.toml"
    config_path.write_text("existing = true")
    monkeypatch.setattr("builtins.input", lambda _: "n")

    rc = run_setup(config_path=config_path)
    assert rc == 1
    assert config_path.read_text() == "existing = true"


def test_run_setup_force_overwrites(tmp_path, monkeypatch):
    config_path = tmp_path / "config.toml"
    config_path.write_text("existing = true")
    inputs = iter(["my-key", "3"])  # API key, install mode = skip
    monkeypatch.setattr("builtins.input", lambda _: next(inputs))
    monkeypatch.setattr("keymic.setup_cli._validate_groq_key", lambda k: True)
    monkeypatch.setattr("keymic.setup_cli._select_hotkey", lambda: "KEY_RIGHTCTRL")
    monkeypatch.setattr("keymic.setup_cli._select_injection", lambda: "auto")
    monkeypatch.setattr("keymic.setup_cli._select_language", lambda: "auto")
    monkeypatch.setattr("keymic.setup_cli._ask_vocab", lambda: [])

    rc = run_setup(config_path=config_path, force=True)
    assert rc == 0
    assert "existing = true" not in config_path.read_text()


def test_run_setup_skip_install_no_pip_call(tmp_path, monkeypatch):
    inputs = iter(["my-key", "3"])  # API key, install mode = 3 = skip
    monkeypatch.setattr("builtins.input", lambda _: next(inputs))
    monkeypatch.setattr("keymic.setup_cli._validate_groq_key", lambda k: True)
    monkeypatch.setattr("keymic.setup_cli._select_hotkey", lambda: "KEY_RIGHTCTRL")
    monkeypatch.setattr("keymic.setup_cli._select_injection", lambda: "auto")
    monkeypatch.setattr("keymic.setup_cli._select_language", lambda: "auto")
    monkeypatch.setattr("keymic.setup_cli._ask_vocab", lambda: [])
    called = {"pip": False}
    monkeypatch.setattr("subprocess.run",
                        lambda *a, **kw: called.__setitem__("pip", True))

    config_path = tmp_path / "config.toml"
    rc = run_setup(config_path=config_path)
    assert rc == 0
    assert called["pip"] is False


def test_run_setup_user_install_runs_pip(tmp_path, monkeypatch):
    inputs = iter(["my-key", "1"])  # API key, install mode = 1 = user-install
    monkeypatch.setattr("builtins.input", lambda _: next(inputs))
    monkeypatch.setattr("keymic.setup_cli._validate_groq_key", lambda k: True)
    monkeypatch.setattr("keymic.setup_cli._select_hotkey", lambda: "KEY_RIGHTCTRL")
    monkeypatch.setattr("keymic.setup_cli._select_injection", lambda: "auto")
    monkeypatch.setattr("keymic.setup_cli._select_language", lambda: "auto")
    monkeypatch.setattr("keymic.setup_cli._ask_vocab", lambda: [])
    calls = []
    class FakeResult:
        returncode = 0
    def fake_run(cmd, **kw):
        calls.append(cmd)
        return FakeResult()
    monkeypatch.setattr("subprocess.run", fake_run)

    config_path = tmp_path / "config.toml"
    rc = run_setup(config_path=config_path)
    assert rc == 0
    assert len(calls) == 1
    cmd = calls[0]
    assert cmd[0] == "pip"
    assert "--user" in cmd
    assert "-e" in cmd


def test_run_setup_skips_install_when_no_pyproject(tmp_path, monkeypatch):
    """_ask_install_mode returns 'skip' when no pyproject.toml in CWD."""
    monkeypatch.chdir(tmp_path)  # cwd has no pyproject.toml
    inputs = iter(["my-key"])  # only API key, no install prompt expected
    monkeypatch.setattr("builtins.input", lambda _: next(inputs))
    monkeypatch.setattr("keymic.setup_cli._validate_groq_key", lambda k: True)
    monkeypatch.setattr("keymic.setup_cli._select_hotkey", lambda: "KEY_RIGHTCTRL")
    monkeypatch.setattr("keymic.setup_cli._select_injection", lambda: "auto")
    monkeypatch.setattr("keymic.setup_cli._select_language", lambda: "auto")
    monkeypatch.setattr("keymic.setup_cli._ask_vocab", lambda: [])
    called = {"pip": False}
    monkeypatch.setattr("subprocess.run",
                        lambda *a, **kw: called.__setitem__("pip", True))

    rc = run_setup(config_path=tmp_path / "config.toml")
    assert rc == 0
    assert called["pip"] is False


def test_ask_install_mode_returns_skip_without_pyproject(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    from keymic.setup_cli import _ask_install_mode
    assert _ask_install_mode(tmp_path) == "skip"


def test_ask_install_mode_prompts_when_pyproject_exists(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "pyproject.toml").write_text("[project]\nname='x'")
    inputs = iter(["2"])  # System-Install
    monkeypatch.setattr("builtins.input", lambda _: next(inputs))
    from keymic.setup_cli import _ask_install_mode
    assert _ask_install_mode(tmp_path) == "system"
