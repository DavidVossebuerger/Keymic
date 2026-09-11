import subprocess
import sys


def test_version_flag():
    result = subprocess.run(
        [sys.executable, "-m", "keymic", "--version"],
        capture_output=True, text=True,
    )
    assert result.returncode == 0
    assert "keymic 0.1.0" in result.stdout


def test_help_flag():
    result = subprocess.run(
        [sys.executable, "-m", "keymic", "--help"],
        capture_output=True, text=True,
    )
    assert result.returncode == 0
    assert "Push-to-talk voice dictation" in result.stdout


def test_unknown_subcommand_exits_nonzero():
    result = subprocess.run(
        [sys.executable, "-m", "keymic", "unknown"],
        capture_output=True, text=True,
    )
    assert result.returncode != 0
