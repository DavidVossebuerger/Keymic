from pathlib import Path
from keymic.config import default_config, merge_config, load_config, save_config


def test_default_config_has_expected_sections():
    cfg = default_config()
    assert "general" in cfg
    assert "groq" in cfg
    assert cfg["general"]["hotkey"] == "KEY_RIGHTCTRL"


def test_default_config_ai_postprocess_is_false():
    cfg = default_config()
    assert cfg["postprocess"]["ai_postprocess"] is False


def test_merge_config_user_overrides_default():
    merged = merge_config(default_config(), {"general": {"hotkey": "KEY_F12"}})
    assert merged["general"]["hotkey"] == "KEY_F12"
    assert "language" in merged["general"]


def test_merge_config_preserves_unknown_sections():
    merged = merge_config(default_config(), {"custom_section": {"foo": 1}})
    assert merged["custom_section"]["foo"] == 1


def test_save_and_load_roundtrip(tmp_path):
    cfg = default_config()
    cfg["general"]["hotkey"] = "KEY_PAUSE"
    path = tmp_path / "config.toml"
    save_config(cfg, path)
    loaded = load_config(path)
    assert loaded["general"]["hotkey"] == "KEY_PAUSE"


def test_load_missing_returns_default(tmp_path):
    cfg = load_config(tmp_path / "nonexistent.toml")
    assert cfg["general"]["hotkey"] == "KEY_RIGHTCTRL"
