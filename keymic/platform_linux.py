"""Linux-specific implementation: evdev, pw-cat, ydotool/xdotool."""
from __future__ import annotations

import logging
import os
import queue
import shutil
import subprocess
import sys
import threading
from pathlib import Path
from typing import Iterator, NamedTuple, Optional

if sys.platform != "linux":
    raise ImportError("platform_linux can only be imported on Linux")

try:
    import evdev  # type: ignore
    from evdev import InputDevice, UInput  # type: ignore
except ImportError as e:
    raise ImportError(
        "evdev is required for platform_linux. Install with: pip install evdev"
    ) from e

log = logging.getLogger("keymic")


class HotkeyEvent(NamedTuple):
    pressed: bool
    key_name: str


class HotkeyListener:
    """Context manager yielding HotkeyEvents from any keyboard device.

    Architektur (wie dictationd.py):
      - EVIOCGRAB beim Startup, für Daemon-Lifetime gehalten
      - UInput-Device "keymic-replayer" für Replay
      - Pro Tastatur ein Reader-Thread
      - Reader-Thread: liest Events, leitet Hotkey-Events an Queue weiter,
        replayt ALLE anderen Tasten via uinput.write + uinput.syn
      - Haupt-Thread konsumiert Hotkey-Events via hotkey_events()

    Ohne Replay der Nicht-Hotkey-Tasten würde der User nicht tippen können
    während der Daemon läuft (alle Tasten wären exklusiv beim Daemon).
    """

    def __init__(self, key_name: str):
        self.key_name = key_name
        self._devices: list = []
        self._stopping = False
        self._grabbed = False
        self._uinput: Optional[UInput] = None
        self._hotkey_queue: "queue.Queue[HotkeyEvent]" = queue.Queue()
        self._threads: list[threading.Thread] = []
        self._hotkey_code: Optional[int] = None
        self._recording = False  # shared state: device threads check this

    def __enter__(self) -> "HotkeyListener":
        target_code = self._resolve_keycode(self.key_name)
        if target_code is None:
            raise ValueError(f"Unknown key: {self.key_name}")
        self._hotkey_code = target_code
        # Discover keyboards
        for path in evdev.list_devices():
            try:
                dev = InputDevice(path)
                caps = dev.capabilities()
                if evdev.ecodes.EV_KEY in caps and target_code in caps[evdev.ecodes.EV_KEY]:
                    self._devices.append(dev)
            except (PermissionError, OSError):
                continue
        if not self._devices:
            raise RuntimeError(
                f"No keyboard device found for {self.key_name}. "
                f"Check user is in 'input' group."
            )
        # Create uinput device for replay
        try:
            self._uinput = UInput(
                events={evdev.ecodes.EV_KEY: list(range(0, 768))},
                name="keymic-replayer",
            )
        except OSError as e:
            log.warning("uinput-Replayer nicht erstellt (%s) — "
                        "Replay deaktiviert, du kannst während Daemon-Lauf "
                        "nicht tippen.", e)
            self._uinput = None
        # Grab all devices
        self.grab()
        # Start one reader thread per device
        for dev in self._devices:
            t = threading.Thread(
                target=self._device_thread,
                args=(dev,),
                name=f"keymic-{dev.path.split('/')[-1]}",
                daemon=True,
            )
            t.start()
            self._threads.append(t)
        log.info("HotkeyListener active on %d device(s)", len(self._devices))
        return self

    def __exit__(self, *exc) -> None:
        self._stopping = True
        # Stop the reader threads (closing devices will unblock read_loop)
        for dev in self._devices:
            try:
                dev.close()
            except Exception:
                pass
        for t in self._threads:
            t.join(timeout=1.0)
        self._threads.clear()
        if self._grabbed:
            self.ungrab()
        if self._uinput is not None:
            try:
                self._uinput.close()
            except Exception:
                pass
            self._uinput = None

    @property
    def is_grabbed(self) -> bool:
        return self._grabbed

    @property
    def is_recording(self) -> bool:
        return self._recording

    def set_recording(self, recording: bool) -> None:
        """Toggle recording state. When True, non-hotkey keys are SWALLOWED
        (not replayed) to prevent accidental keypresses from leaking into
        the focused app during dictation."""
        self._recording = recording

    def hotkey_events(self) -> Iterator[HotkeyEvent]:
        """Generator yielding HotkeyEvents from any device thread."""
        while not self._stopping:
            try:
                ev = self._hotkey_queue.get(timeout=0.1)
                yield ev
            except queue.Empty:
                continue

    def _device_thread(self, dev: InputDevice) -> None:
        """Reader-Thread pro Tastatur-Device.

        Verarbeitet Events:
          - Hotkey-Code: in Queue legen (nicht replayen)
          - Andere EV_KEY: wenn nicht recording → replay via uinput
          - Andere Event-Typen: droppen
        """
        try:
            for event in dev.read_loop():
                if self._stopping:
                    break
                if event.type != evdev.ecodes.EV_KEY:
                    continue
                # Hotkey: nur in Queue, nie replayen
                if event.code == self._hotkey_code:
                    if event.value == 1:
                        self._hotkey_queue.put(HotkeyEvent(
                            pressed=True, key_name=self.key_name,
                        ))
                    elif event.value == 0:
                        self._hotkey_queue.put(HotkeyEvent(
                            pressed=False, key_name=self.key_name,
                        ))
                    continue
                # Während Recording: alle anderen Tasten schlucken
                if self._recording:
                    continue
                # Replay via uinput
                if self._uinput is not None:
                    try:
                        self._uinput.write(evdev.ecodes.EV_KEY, event.code, event.value)
                        self._uinput.syn()
                    except OSError:
                        pass
        except OSError:
            # Device wurde geschlossen (z. B. beim __exit__)
            pass
        except Exception as e:
            log.error("device-thread %s aborted: %s", dev.path, e)

    def grab(self) -> None:
        """Acquire exclusive control (EVIOCGRAB) of all keyboard devices."""
        if self._grabbed:
            return
        grabbed_paths: list[str] = []
        errors: list[tuple[str, str]] = []
        for dev in self._devices:
            try:
                dev.grab()
                grabbed_paths.append(dev.path)
            except (OSError, IOError) as e:
                errors.append((dev.path, str(e)))
        if errors:
            for dev in self._devices:
                if dev.path in grabbed_paths:
                    try:
                        dev.ungrab()
                    except Exception:
                        pass
            msg = "; ".join(f"{p}: {e}" for p, e in errors)
            raise RuntimeError(
                f"Failed to grab keyboard ({len(errors)} of {len(self._devices)} "
                f"devices failed): {msg}"
            )
        self._grabbed = True
        log.info("Grabbed %d keyboard device(s)", len(self._devices))

    def ungrab(self) -> None:
        """Release exclusive control of all keyboard devices."""
        if not self._grabbed:
            return
        for dev in self._devices:
            try:
                dev.ungrab()
            except Exception:
                pass
        self._grabbed = False
        log.info("Released keyboard grab")

    @staticmethod
    def _resolve_keycode(key_name: str) -> Optional[int]:
        """Map 'KEY_RIGHTCTRL' -> evdev code."""
        name = key_name.upper()
        if not name.startswith("KEY_"):
            name = "KEY_" + name
        code = getattr(evdev.ecodes, name, None)
        return int(code) if code is not None else None


class AudioRecorder:
    """Records audio via pw-cat to a WAV file."""

    def __init__(self, device: str, sample_rate: int, output_path: Path):
        self.device = device
        self.sample_rate = sample_rate
        self.output_path = Path(output_path)
        self._proc: Optional[subprocess.Popen] = None

    def __enter__(self) -> "AudioRecorder":
        args = [
            "pw-cat", "--record",
            "--format", "s16",
            "--rate", str(self.sample_rate),
            "--channels", "1",
            str(self.output_path),
        ]
        if self.device != "auto":
            args.extend(["--target", self.device])
        self._proc = subprocess.Popen(args)
        return self

    def stop(self) -> None:
        if self._proc and self._proc.poll() is None:
            self._proc.terminate()
            try:
                self._proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._proc.kill()

    def __exit__(self, *exc) -> None:
        self.stop()


class TextInjector:
    """Cross-DE injection: ydotool (Wayland) / xdotool (X11) / clipboard."""

    def __init__(self, method: str):
        self.method = method
        self._resolved: Optional[str] = None

    def __enter__(self) -> "TextInjector":
        if self.method == "auto":
            self._resolved = self._resolve_method()
        else:
            self._resolved = self.method
        return self

    def __exit__(self, *exc) -> None:
        pass

    def type(self, text: str) -> None:
        if self._resolved is None:
            self._resolved = self._resolve_method() if self.method == "auto" else self.method
        if self._resolved == "xdotool":
            # xdotool nutzt XTest (kein uinput) — kollidiert NICHT mit
            # keymics uinput-Device. --clearmodifiers neutralisiert alle
            # noch hängenden Modifier.
            subprocess.run(["xdotool", "type", "--clearmodifiers", "--", text], check=True)
        elif self._resolved == "clipboard":
            self._clipboard_paste(text)
        elif self._resolved == "ydotool":
            # ydotool type via uinput kollidiert oft mit keymics eigenem
            # uinput-Device → nur 1 Zeichen kommt durch. Auf Wayland ist
            # clipboard (wl-copy + ctrl+v) der Workaround.
            self._clipboard_paste(text)
        else:
            raise RuntimeError(f"No injection method available. Tried: {self.method}")

    def _resolve_method(self) -> str:
        # Display-Server erkennen: Wayland → wl-copy bevorzugen, X11 → xdotool.
        is_wayland = bool(os.environ.get("WAYLAND_DISPLAY"))
        if is_wayland:
            if shutil.which("wl-copy") or shutil.which("xclip"):
                return "clipboard"
            if shutil.which("ydotool"):
                return "ydotool"
        else:
            if shutil.which("xdotool"):
                return "xdotool"
            if shutil.which("xclip") or shutil.which("wl-copy"):
                return "clipboard"
        raise RuntimeError(
            "No injection tool found. Install xdotool (X11) or "
            "wl-clipboard (Wayland)."
        )

    @staticmethod
    def _clipboard_paste(text: str) -> None:
        if shutil.which("wl-copy"):
            subprocess.run(["wl-copy"], input=text.encode("utf-8"), check=True)
        elif shutil.which("xclip"):
            subprocess.run(
                ["xclip", "-selection", "clipboard"],
                input=text.encode("utf-8"), check=True,
            )
        else:
            raise RuntimeError("No clipboard tool found (need wl-copy or xclip)")
        for tool, cmd in [
            ("wtype", ["wtype", "-k", "ctrl+v"]),
            ("xdotool", ["xdotool", "key", "--clearmodifiers", "ctrl+v"]),
            ("ydotool", ["ydotool", "key", "ctrl+v"]),
        ]:
            if shutil.which(tool):
                subprocess.run(cmd, check=True)
                return
        raise RuntimeError("No key-sending tool found (need wtype, xdotool, or ydotool)")
