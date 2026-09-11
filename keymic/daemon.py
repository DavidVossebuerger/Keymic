"""Daemon kernel: state machine, orchestration."""
from __future__ import annotations

import logging
import os
import sys
from enum import Enum
from pathlib import Path
from typing import Optional

from keymic.cleanup import cleanup as cleanup_text
from keymic.whisper_api import transcribe as whisper_transcribe

log = logging.getLogger("keymic")


class DaemonState(Enum):
    IDLE = "idle"
    RECORDING = "recording"
    PROCESSING = "processing"


class DictationDaemon:
    """Orchestriert Hotkey -> Audio -> Whisper -> Cleanup -> Inject."""

    def __init__(self, cfg: dict, *, output_dir: Optional[Path] = None):
        self.cfg = cfg
        self.output_dir = Path(output_dir) if output_dir else Path("/tmp")
        self.state = DaemonState.IDLE
        self._wav_path: Optional[Path] = None
        self._audio = None
        self._inject = None
        self._listener = None

    def run(self) -> None:
        """Blocking main loop."""
        if sys.platform != "linux":
            raise RuntimeError("Daemon requires Linux")
        from keymic.audio import AudioSession
        from keymic.platform_linux import HotkeyListener, TextInjector

        hotkey = self.cfg["general"]["hotkey"]
        device = self.cfg["general"]["audio_device"]
        sample_rate = self.cfg["general"]["sample_rate"]
        max_s = self.cfg["general"]["max_recording_seconds"]

        log.info("Keymic starting (hotkey=%s)", hotkey)

        with HotkeyListener(hotkey) as listener, \
             TextInjector(self.cfg["injection"]["method"]) as injector:
            self._listener = listener
            self._inject = injector
            # Listener greift Tastatur + startet per-device Threads + uinput-Replay.
            # Wir konsumieren hier nur die Hotkey-Events.
            for ev in listener.hotkey_events():
                if ev.key_name != hotkey:
                    continue
                if ev.pressed and self.state == DaemonState.IDLE:
                    self._audio = AudioSession(
                        device=device, sample_rate=sample_rate,
                        max_seconds=max_s, output_dir=self.output_dir,
                    )
                    self._handle_hotkey_down()
                elif not ev.pressed and self.state == DaemonState.RECORDING:
                    self._handle_hotkey_up()
            # Cleanup: Grab + uinput + Threads via HotkeyListener.__exit__

    def _handle_hotkey_down(self) -> None:
        if self.state != DaemonState.IDLE or self._audio is None:
            return
        self._wav_path = self._audio.start()
        self.state = DaemonState.RECORDING
        if self._listener is not None:
            self._listener.set_recording(True)
        log.info("Recording started: %s", self._wav_path)

    def _handle_hotkey_up(self) -> None:
        if self.state != DaemonState.RECORDING or self._audio is None:
            return
        wav_path = self._audio.stop()
        self.state = DaemonState.PROCESSING
        if self._listener is not None:
            self._listener.set_recording(False)
        log.info("Recording stopped: %s", wav_path)
        cleaned = self._process_recording(wav_path)
        if cleaned:
            assert self._inject is not None
            self._inject.type(cleaned)
            log.info("Injected %d chars", len(cleaned))
        self._wav_path = None
        self.state = DaemonState.IDLE

    def _transcribe(self, wav_path: Path) -> str:
        groq = self.cfg["groq"]
        api_key = groq.get("api_key") or _api_key_from_env()
        if not api_key:
            raise RuntimeError("No Groq API key configured (groq.api_key or $GROQ_API_KEY)")
        text = whisper_transcribe(
            wav_path,
            api_key=api_key,
            endpoint=groq["endpoint"],
            model=groq["model"],
            prompt=groq.get("prompt", ""),
            language=self.cfg["general"].get("language"),
        )
        log.info("Whisper transcript (%d chars): %r", len(text), text)
        return text

    def _cleanup(self, text: str) -> str:
        post = self.cfg["postprocess"]
        cleaned = cleanup_text(
            text,
            mode="normal",
            api_key=self.cfg["groq"].get("api_key") or _api_key_from_env(),
            use_ai=post.get("ai_postprocess", False),
            custom_dict=post.get("ai_custom_dict"),
        )
        log.info("Cleanup output (%d chars): %r", len(cleaned), cleaned)
        return cleaned

    def _process_recording(self, wav_path: Path) -> str:
        try:
            raw = self._transcribe(wav_path)
        except Exception as e:
            log.error("Transcribe failed: %s", e)
            return ""
        if not raw:
            return ""
        try:
            return self._cleanup(raw)
        except Exception as e:
            log.error("Cleanup failed: %s", e)
            return raw


def _api_key_from_env() -> str:
    return os.environ.get("GROQ_API_KEY", "")
