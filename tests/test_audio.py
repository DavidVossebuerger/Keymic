from pathlib import Path
from unittest.mock import MagicMock, patch
from keymic.audio import AudioSession


def test_audio_session_starts_and_stops(tmp_path):
    sess = AudioSession(device="auto", sample_rate=16000, max_seconds=600, output_dir=tmp_path)
    with patch("keymic.audio.AudioRecorder") as mock_rec:
        mock_instance = MagicMock()
        mock_rec.return_value = mock_instance
        mock_instance.__enter__ = MagicMock(return_value=mock_instance)
        mock_instance.__exit__ = MagicMock(return_value=False)

        wav_path = sess.start()
        assert sess.is_recording
        assert isinstance(wav_path, Path)
        assert wav_path.parent == tmp_path

        out_path = sess.stop()
        assert sess.is_recording is False
        assert out_path == wav_path


def test_audio_session_stop_without_start_raises(tmp_path):
    sess = AudioSession(device="auto", sample_rate=16000, max_seconds=600, output_dir=tmp_path)
    try:
        sess.stop()
    except RuntimeError:
        return
    raise AssertionError("Expected RuntimeError")


def test_audio_session_elapsed_increases(tmp_path):
    sess = AudioSession(device="auto", sample_rate=16000, max_seconds=600, output_dir=tmp_path)
    assert sess.elapsed() == 0.0
    with patch("keymic.audio.AudioRecorder") as mock_rec:
        mock_instance = MagicMock()
        mock_rec.return_value = mock_instance
        mock_instance.__enter__ = MagicMock(return_value=mock_instance)
        mock_instance.__exit__ = MagicMock(return_value=False)
        sess.start()
        assert sess.elapsed() >= 0.0
        sess.stop()
        assert sess.elapsed() == 0.0
