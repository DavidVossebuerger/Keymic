"""Audio recording lifecycle (thin wrapper over platform_linux)."""
from __future__ import annotations

import sys
import time
import uuid
from pathlib import Path

if sys.platform == "linux":
    from keymic.platform_linux import AudioRecorder
else:
    AudioRecorder = None  # type: ignore


class AudioSession:
    """Manages a single recording session."""

    def __init__(self, device: str, sample_rate: int, max_seconds: int, output_dir: Path):
        self.device = device
        self.sample_rate = sample_rate
        self.max_seconds = max_seconds
        self.output_dir = Path(output_dir)
        self._recorder = None
        self._started_at: float = 0.0
        self._wav_path: Path | None = None

    @property
    def is_recording(self) -> bool:
        return self._recorder is not None

    def start(self) -> Path:
        if AudioRecorder is None:
            raise RuntimeError("AudioSession: platform_linux not available on this OS")
        self.output_dir.mkdir(parents=True, exist_ok=True)
        ts = time.strftime("%Y%m%d-%H%M%S")
        self._wav_path = self.output_dir / f"keymic-{ts}-{uuid.uuid4().hex[:8]}.wav"
        self._recorder = AudioRecorder(
            device=self.device,
            sample_rate=self.sample_rate,
            output_path=self._wav_path,
        )
        self._recorder.__enter__()
        self._started_at = time.time()
        return self._wav_path

    def stop(self) -> Path:
        if self._recorder is None:
            raise RuntimeError("Not recording")
        self._recorder.__exit__(None, None, None)
        self._recorder = None
        if self._wav_path is None:
            raise RuntimeError("Internal error: no WAV path")
        return self._wav_path

    def elapsed(self) -> float:
        if not self.is_recording:
            return 0.0
        return time.time() - self._started_at
