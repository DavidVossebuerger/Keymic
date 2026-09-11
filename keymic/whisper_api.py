"""Groq Whisper API client."""
from __future__ import annotations

from pathlib import Path
from typing import Optional

import requests


class WhisperError(Exception):
    """Raised when the Whisper API returns an error or unexpected response."""


def transcribe(
    audio_path: Path,
    *,
    api_key: str,
    endpoint: str,
    model: str,
    prompt: str = "",
    language: Optional[str] = None,
    session: Optional[requests.Session] = None,
    timeout_s: float = 30.0,
) -> str:
    """Send audio file to Whisper-compatible API, return transcribed text."""
    audio_path = Path(audio_path)
    if not audio_path.exists():
        raise FileNotFoundError(f"Audio file missing: {audio_path}")
    sess = session or requests
    with open(audio_path, "rb") as f:
        data: dict = {"model": model}
        if prompt:
            data["prompt"] = prompt
        if language and language != "auto":
            data["language"] = language
        try:
            r = sess.post(
                endpoint,
                headers={"Authorization": f"Bearer {api_key}"},
                data=data,
                files={"file": (audio_path.name, f, "audio/wav")},
                timeout=timeout_s,
            )
        except requests.RequestException as e:
            raise WhisperError(f"Network error: {e}") from e
    if r.status_code != 200:
        raise WhisperError(f"API {r.status_code}: {r.text[:200]}")
    try:
        return r.json()["text"].strip()
    except (KeyError, ValueError) as e:
        raise WhisperError(f"Unexpected response shape: {e}") from e
