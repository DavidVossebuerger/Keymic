from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest
from keymic.daemon import DictationDaemon, DaemonState


@pytest.fixture
def base_cfg():
    return {
        "general": {"hotkey": "KEY_RIGHTCTRL", "max_recording_seconds": 600,
                     "audio_device": "auto", "sample_rate": 16000,
                     "language": "de"},
        "groq": {"api_key": "test-key", "model": "whisper-large-v3",
                 "endpoint": "https://e", "prompt": ""},
        "injection": {"method": "clipboard"},
        "postprocess": {"remove_fillers": True, "filler_words": [], "auto_capitalize": True,
                        "auto_punctuate": True, "ai_postprocess": False,
                        "ai_custom_dict": [], "ai_skip_if_clean": False,
                        "ai_model": "m", "ai_endpoint": "https://e", "ai_timeout_s": 10},
        "ui": {"notify": True, "state_file": "/tmp/keymic-test.state"},
        "learn": {"json_path": "/tmp/keymic-test-learn.json", "window_s": 0.0},
    }


def test_daemon_initial_state_is_idle(base_cfg):
    d = DictationDaemon(base_cfg)
    assert d.state == DaemonState.IDLE


def test_daemon_handle_hotkey_down_starts_recording(base_cfg, tmp_path):
    d = DictationDaemon(base_cfg, output_dir=tmp_path)
    with patch.object(d, "_audio") as mock_audio:
        mock_audio.start.return_value = tmp_path / "out.wav"
        mock_audio.is_recording = True
        d._handle_hotkey_down()
        assert d.state == DaemonState.RECORDING
        mock_audio.start.assert_called_once()


def test_daemon_handle_hotkey_up_stops_and_processes(base_cfg, tmp_path):
    d = DictationDaemon(base_cfg, output_dir=tmp_path)
    wav = tmp_path / "out.wav"
    wav.write_bytes(b"RIFF")
    d._wav_path = wav
    d._audio = MagicMock()
    d._audio.stop.return_value = wav
    d._inject = MagicMock()
    d.state = DaemonState.RECORDING

    with patch.object(d, "_transcribe", return_value="Hallo Welt"), \
         patch.object(d, "_cleanup", return_value="Hallo Welt."):
        d._handle_hotkey_up()
        assert d.state == DaemonState.IDLE
        d._inject.type.assert_called_once_with("Hallo Welt.")


def test_daemon_process_recording_handles_empty_transcript(base_cfg, tmp_path):
    d = DictationDaemon(base_cfg, output_dir=tmp_path)
    wav = tmp_path / "out.wav"
    wav.write_bytes(b"RIFF")
    with patch.object(d, "_transcribe", return_value=""):
        result = d._process_recording(wav)
        assert result == ""


def test_daemon_process_recording_handles_transcribe_error(base_cfg, tmp_path):
    d = DictationDaemon(base_cfg, output_dir=tmp_path)
    wav = tmp_path / "out.wav"
    wav.write_bytes(b"RIFF")
    with patch.object(d, "_transcribe", side_effect=RuntimeError("api down")):
        result = d._process_recording(wav)
        assert result == ""


def test_daemon_transcribe_uses_env_when_config_empty(base_cfg, tmp_path, monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "env-key")
    base_cfg["groq"]["api_key"] = ""
    d = DictationDaemon(base_cfg, output_dir=tmp_path)
    with patch("keymic.daemon.whisper_transcribe") as mock_wt:
        mock_wt.return_value = "Hallo"
        d._transcribe(tmp_path / "x.wav")
        call_kwargs = mock_wt.call_args.kwargs
        assert call_kwargs["api_key"] == "env-key"


def test_daemon_no_api_key_raises(base_cfg, tmp_path, monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    base_cfg["groq"]["api_key"] = ""
    d = DictationDaemon(base_cfg, output_dir=tmp_path)
    try:
        d._transcribe(tmp_path / "x.wav")
    except RuntimeError as e:
        assert "API key" in str(e)
        return
    raise AssertionError("Expected RuntimeError for missing API key")


def test_daemon_hotkey_down_toggles_recording(base_cfg, tmp_path):
    """_handle_hotkey_down must signal listener to start swallowing non-hotkey keys."""
    d = DictationDaemon(base_cfg, output_dir=tmp_path)
    mock_listener = MagicMock()
    d._listener = mock_listener
    d._audio = MagicMock()
    d._audio.start.return_value = tmp_path / "out.wav"
    d._handle_hotkey_down()
    mock_listener.set_recording.assert_called_once_with(True)
    assert d.state == DaemonState.RECORDING


def test_daemon_hotkey_up_toggles_recording_off(base_cfg, tmp_path):
    """_handle_hotkey_up must signal listener to resume replaying non-hotkey keys."""
    d = DictationDaemon(base_cfg, output_dir=tmp_path)
    mock_listener = MagicMock()
    d._listener = mock_listener
    d._audio = MagicMock()
    d._audio.stop.return_value = tmp_path / "x.wav"
    d._inject = MagicMock()
    d.state = DaemonState.RECORDING

    with patch.object(d, "_transcribe", return_value="hi"), \
         patch.object(d, "_cleanup", return_value="hi."):
        d._handle_hotkey_up()
    mock_listener.set_recording.assert_called_once_with(False)
    assert d.state == DaemonState.IDLE


def test_daemon_run_uses_listener_hotkey_events(base_cfg, tmp_path, monkeypatch):
    """run() consumes from listener.hotkey_events() and processes the events."""
    monkeypatch.setenv("GROQ_API_KEY", "k")
    d = DictationDaemon(base_cfg, output_dir=tmp_path)
    from keymic.platform_linux import HotkeyEvent

    mock_listener = MagicMock()
    mock_listener.__enter__ = MagicMock(return_value=mock_listener)
    mock_listener.__exit__ = MagicMock(return_value=False)
    # Emit one press then one release
    mock_listener.hotkey_events.return_value = iter([
        HotkeyEvent(pressed=True, key_name="KEY_RIGHTCTRL"),
        HotkeyEvent(pressed=False, key_name="KEY_RIGHTCTRL"),
    ])
    mock_injector = MagicMock()
    mock_injector.__enter__ = MagicMock(return_value=mock_injector)
    mock_injector.__exit__ = MagicMock(return_value=False)
    with patch("keymic.platform_linux.HotkeyListener", return_value=mock_listener), \
         patch("keymic.platform_linux.TextInjector", return_value=mock_injector), \
         patch("keymic.audio.AudioSession"), \
         patch.object(d, "_process_recording", return_value="text"):
        d.run()
    # Hotkey was processed (state went IDLE → RECORDING → IDLE)
    assert d.state == DaemonState.IDLE
    mock_listener.set_recording.assert_any_call(True)
    mock_listener.set_recording.assert_any_call(False)
    mock_injector.type.assert_called_once_with("text")
