from pathlib import Path
from unittest.mock import MagicMock
import pytest
from keymic.whisper_api import transcribe, WhisperError


@pytest.fixture
def fake_audio(tmp_path):
    p = tmp_path / "test.wav"
    p.write_bytes(b"RIFF\x00\x00\x00\x00WAVE")
    return p


def test_transcribe_success(fake_audio):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"text": "Hallo Welt"}
    session = MagicMock()
    session.post.return_value = mock_resp

    result = transcribe(
        fake_audio,
        api_key="test-key",
        endpoint="https://api.example.com/transcriptions",
        model="whisper-large-v3",
        session=session,
    )
    assert result == "Hallo Welt"


def test_transcribe_api_error_raises_whisper_error(fake_audio):
    mock_resp = MagicMock()
    mock_resp.status_code = 401
    mock_resp.text = "Unauthorized"
    session = MagicMock()
    session.post.return_value = mock_resp

    with pytest.raises(WhisperError):
        transcribe(
            fake_audio,
            api_key="bad-key",
            endpoint="https://api.example.com/transcriptions",
            model="whisper-large-v3",
            session=session,
        )


def test_transcribe_passes_language_and_prompt(fake_audio):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"text": "ok"}
    session = MagicMock()
    session.post.return_value = mock_resp

    transcribe(
        fake_audio,
        api_key="k",
        endpoint="https://api.example.com",
        model="m",
        prompt="Eigenname: FooBar",
        language="de",
        session=session,
    )
    call_kwargs = session.post.call_args.kwargs
    data = call_kwargs["data"]
    assert data["language"] == "de"
    assert data["prompt"] == "Eigenname: FooBar"
    assert data["model"] == "m"
    assert call_kwargs["headers"]["Authorization"] == "Bearer k"


def test_transcribe_missing_file_raises():
    with pytest.raises(FileNotFoundError):
        transcribe(
            Path("/nonexistent.wav"),
            api_key="k",
            endpoint="https://e",
            model="m",
        )


def test_transcribe_skips_language_when_auto(fake_audio):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"text": "ok"}
    session = MagicMock()
    session.post.return_value = mock_resp

    transcribe(
        fake_audio,
        api_key="k",
        endpoint="https://e",
        model="m",
        language="auto",
        session=session,
    )
    call_kwargs = session.post.call_args.kwargs
    assert "language" not in call_kwargs["data"]
