from unittest.mock import MagicMock, patch
import pytest


pytestmark = pytest.mark.skipif(
    __import__("sys").platform != "linux",
    reason="platform_linux is Linux-only",
)


def test_hotkey_event_construction():
    from keymic.platform_linux import HotkeyEvent
    ev = HotkeyEvent(pressed=True, key_name="KEY_RIGHTCTRL")
    assert ev.pressed is True
    assert ev.key_name == "KEY_RIGHTCTRL"


def test_audio_recorder_starts_pwcat(tmp_path):
    from keymic.platform_linux import AudioRecorder
    out = tmp_path / "test.wav"
    with patch("subprocess.Popen") as mock_popen:
        mock_proc = MagicMock()
        mock_popen.return_value = mock_proc
        rec = AudioRecorder(device="auto", sample_rate=16000, output_path=out)
        rec.__enter__()
        mock_popen.assert_called_once()
        args = mock_popen.call_args.args[0]
        assert "pw-cat" in args
        assert "--record" in args
        rec.__exit__(None, None, None)


def test_audio_recorder_stop_terminates(tmp_path):
    from keymic.platform_linux import AudioRecorder
    out = tmp_path / "test.wav"
    with patch("subprocess.Popen") as mock_popen:
        mock_proc = MagicMock()
        mock_proc.poll.return_value = None  # process still running
        mock_popen.return_value = mock_proc
        rec = AudioRecorder(device="auto", sample_rate=16000, output_path=out)
        rec.__enter__()
        rec.stop()
        mock_proc.terminate.assert_called_once()
        mock_proc.wait.assert_called_once()


def test_text_injector_ydotool_uses_clipboard():
    """ydotool method also goes via clipboard to avoid uinput-device conflict."""
    from keymic.platform_linux import TextInjector
    with patch("subprocess.run") as mock_run:
        inj = TextInjector(method="ydotool")
        inj.__enter__()
        inj.type("hello")
        # First call: wl-copy with UTF-8 bytes
        first_call = mock_run.call_args_list[0]
        assert first_call.args[0] == ["wl-copy"]
        assert first_call.kwargs["input"] == b"hello"
        # Second call: ctrl+v via xdotool (preferred over ydotool for paste)
        second_call = mock_run.call_args_list[1]
        assert second_call.args[0][:2] == ["xdotool", "key"]
        assert "ctrl+v" in second_call.args[0]
        inj.__exit__(None, None, None)


def test_text_injector_ydotool_uses_utf8_encoding():
    """UTF-8 encoding for Unicode safety."""
    from keymic.platform_linux import TextInjector
    with patch("subprocess.run") as mock_run:
        inj = TextInjector(method="ydotool")
        inj.__enter__()
        inj.type("Ich zeig dir mein ß-Objekt.")
        kwargs = mock_run.call_args_list[0].kwargs
        assert isinstance(kwargs["input"], bytes)
        assert kwargs["input"] == "Ich zeig dir mein ß-Objekt.".encode("utf-8")
        inj.__exit__(None, None, None)


def test_text_injector_xdotool_uses_clearmodifiers():
    from keymic.platform_linux import TextInjector
    with patch("subprocess.run") as mock_run:
        inj = TextInjector(method="xdotool")
        inj.__enter__()
        inj.type("hello")
        args = mock_run.call_args.args[0]
        assert args[0] == "xdotool"
        assert "--clearmodifiers" in args
        inj.__exit__(None, None, None)


def test_text_injector_clipboard_method():
    """Explicit 'clipboard' method uses wl-copy + ctrl+v."""
    from keymic.platform_linux import TextInjector
    with patch("subprocess.run") as mock_run:
        inj = TextInjector(method="clipboard")
        inj.__enter__()
        inj.type("so jetzt testen wir mal")
        first_call = mock_run.call_args_list[0]
        assert first_call.args[0] == ["wl-copy"]
        assert first_call.kwargs["input"] == b"so jetzt testen wir mal"
        inj.__exit__(None, None, None)


def test_text_injector_method_resolution_x11_prefers_xdotool(monkeypatch):
    """X11: auto-Method picks xdotool (kein uinput-Konflikt)."""
    from keymic.platform_linux import TextInjector
    monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)
    with patch("shutil.which") as mock_which:
        mock_which.side_effect = lambda t: f"/usr/bin/{t}" if t in ("xdotool", "wl-copy", "ydotool") else None
        inj = TextInjector(method="auto")
        assert inj._resolve_method() == "xdotool"


def test_text_injector_method_resolution_wayland_prefers_clipboard(monkeypatch):
    """Wayland: auto-Method picks clipboard (wl-copy + ctrl+v)."""
    from keymic.platform_linux import TextInjector
    monkeypatch.setenv("WAYLAND_DISPLAY", "wayland-0")
    with patch("shutil.which") as mock_which:
        mock_which.side_effect = lambda t: f"/usr/bin/{t}" if t in ("xdotool", "wl-copy", "ydotool") else None
        inj = TextInjector(method="auto")
        assert inj._resolve_method() == "clipboard"


def test_text_injector_method_resolution_x11_falls_back_to_clipboard(monkeypatch):
    """X11 ohne xdotool: fallback auf xclip."""
    from keymic.platform_linux import TextInjector
    monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)
    with patch("shutil.which") as mock_which:
        mock_which.side_effect = lambda t: "/usr/bin/xclip" if t == "xclip" else None
        inj = TextInjector(method="auto")
        assert inj._resolve_method() == "clipboard"


def test_text_injector_no_tool_raises(monkeypatch):
    from keymic.platform_linux import TextInjector
    monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)
    with patch("shutil.which", return_value=None):
        inj = TextInjector(method="auto")
        with pytest.raises(RuntimeError):
            inj._resolve_method()


def test_hotkey_listener_grab_calls_evdev_grab():
    """grab() should call dev.grab() on each keyboard device."""
    from keymic.platform_linux import HotkeyListener
    listener = HotkeyListener("KEY_RIGHTCTRL")
    mock_dev1 = MagicMock()
    mock_dev1.path = "/dev/input/event1"
    mock_dev2 = MagicMock()
    mock_dev2.path = "/dev/input/event2"
    listener._devices = [mock_dev1, mock_dev2]
    listener.grab()
    mock_dev1.grab.assert_called_once()
    mock_dev2.grab.assert_called_once()
    assert listener.is_grabbed is True


def test_hotkey_listener_ungrab_releases_all():
    from keymic.platform_linux import HotkeyListener
    listener = HotkeyListener("KEY_RIGHTCTRL")
    mock_dev = MagicMock()
    listener._devices = [mock_dev]
    listener.grab()
    listener.ungrab()
    mock_dev.ungrab.assert_called_once()
    assert listener.is_grabbed is False


def test_hotkey_listener_grab_rolls_back_on_partial_failure():
    """If one device's grab fails, all already-grabbed devices must be released."""
    from keymic.platform_linux import HotkeyListener
    listener = HotkeyListener("KEY_RIGHTCTRL")
    mock_dev_ok = MagicMock()
    mock_dev_ok.path = "/dev/input/event1"
    mock_dev_fail = MagicMock()
    mock_dev_fail.path = "/dev/input/event2"
    mock_dev_fail.grab.side_effect = OSError("busy")
    listener._devices = [mock_dev_ok, mock_dev_fail]
    with pytest.raises(RuntimeError, match="Failed to grab"):
        listener.grab()
    mock_dev_ok.grab.assert_called_once()
    mock_dev_ok.ungrab.assert_called_once()  # rolled back
    assert listener.is_grabbed is False


def test_hotkey_listener_grab_idempotent():
    """Calling grab() twice doesn't double-grab."""
    from keymic.platform_linux import HotkeyListener
    listener = HotkeyListener("KEY_RIGHTCTRL")
    mock_dev = MagicMock()
    listener._devices = [mock_dev]
    listener.grab()
    listener.grab()
    assert mock_dev.grab.call_count == 1


def test_hotkey_listener_ungrab_when_not_grabbed_is_noop():
    """ungrab() without prior grab() is safe (idempotent)."""
    from keymic.platform_linux import HotkeyListener
    listener = HotkeyListener("KEY_RIGHTCTRL")
    mock_dev = MagicMock()
    listener._devices = [mock_dev]
    listener.ungrab()
    mock_dev.ungrab.assert_not_called()
    assert listener.is_grabbed is False


def test_hotkey_listener_exit_releases_grab():
    """__exit__ must ungrab if currently grabbed."""
    from keymic.platform_linux import HotkeyListener
    listener = HotkeyListener("KEY_RIGHTCTRL")
    mock_dev = MagicMock()
    listener._devices = [mock_dev]
    listener.grab()
    listener.__exit__(None, None, None)
    mock_dev.ungrab.assert_called_once()
    mock_dev.close.assert_called_once()
    assert listener.is_grabbed is False
