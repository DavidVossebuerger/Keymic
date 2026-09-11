"""Config loading, saving, and default merging."""
from __future__ import annotations

import os
import sys
import tomllib
from pathlib import Path
from typing import Any

import tomli_w

if sys.version_info >= (3, 11):
    pass  # tomllib is stdlib
else:  # pragma: no cover
    import tomli as _tomllib  # type: ignore
    tomllib = _tomllib  # type: ignore


DEFAULT_CONFIG_PATH = Path.home() / ".config" / "keymic" / "config.toml"


def default_config() -> dict[str, Any]:
    """Hardcoded defaults. Source of truth."""
    return {
        "general": {
            "language": "de",
            "hotkey_mode": "push-to-talk",
            "hotkey": "KEY_RIGHTCTRL",
            "audio_device": "auto",
            "sample_rate": 16000,
            "max_recording_seconds": 600,
        },
        "groq": {
            "model": "whisper-large-v3",
            "endpoint": "https://api.groq.com/openai/v1/audio/transcriptions",
            "api_key": "",
            "prompt": "",
            "vocab": [],
        },
        "injection": {
            "method": "auto",
            "ydotool_delay_ms": 0,
            "clipboard_paste_delay_ms": 120,
        },
        "postprocess": {
            "remove_fillers": True,
            "filler_words": ["aehm", "aeh", "also", "halt", "quasi", "sozusagen", "eigentlich", "irgendwie"],
            "auto_capitalize": True,
            "auto_punctuate": False,
            "ai_postprocess": False,
            "ai_model": "llama-3.3-70b-versatile",
            "ai_endpoint": "https://api.groq.com/openai/v1/chat/completions",
            "ai_timeout_s": 15,
            "ai_custom_dict": [],
            "ai_skip_if_clean": True,
        },
        "ui": {
            "notify": True,
            "state_file": "/tmp/keymic.state",
        },
        "learn": {
            "json_path": "~/.local/share/keymic/learned.json",
            "window_s": 3.0,
        },
    }


def merge_config(default: dict, user: dict) -> dict:
    """Deep-merge: user overrides default at leaf level."""
    out = {k: v for k, v in default.items()}
    for k, v in user.items():
        if k in out and isinstance(out[k], dict) and isinstance(v, dict):
            out[k] = merge_config(out[k], v)
        else:
            out[k] = v
    return out


def load_config(path: Path | None) -> dict:
    """Load config from path, merge with defaults. Returns defaults if file missing."""
    defaults = default_config()
    if path is None or not Path(path).exists():
        return defaults
    with open(path, "rb") as f:
        user_cfg = tomllib.load(f)
    return merge_config(defaults, user_cfg)


def save_config(cfg: dict, path: Path) -> None:
    """Save config dict as TOML to path."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "wb") as f:
        tomli_w.dump(cfg, f)
