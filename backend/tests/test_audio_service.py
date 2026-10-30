"""Unit tests for AudioService and MockASR transcription."""

import math
import struct
import wave
from pathlib import Path

import pytest

from app.core.config import settings
from app.services.audio_service import (
    MockASR,
    get_audio_service,
    probe_audio_duration_seconds,
)


def create_synthetic_wav(
    file_path: Path,
    duration_sec: float = 2.0,
    sample_rate: int = 16000,
    freq: float = 440.0,
) -> Path:
    """Generate a clean synthetic sine-wave WAV file using only python stdlib."""
    with wave.open(str(file_path), "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        num_frames = int(duration_sec * sample_rate)
        frames = bytearray()
        for i in range(num_frames):
            t = float(i) / sample_rate
            val = int(32767.0 * 0.3 * math.sin(2.0 * math.pi * freq * t))
            frames.extend(struct.pack("<h", val))
        wav_file.writeframes(frames)
    return file_path


def test_probe_audio_duration(tmp_path: Path) -> None:
    wav_path = tmp_path / "sample.wav"
    create_synthetic_wav(wav_path, duration_sec=3.5)
    duration = probe_audio_duration_seconds(wav_path)
    assert 3.3 <= duration <= 3.7


def test_mock_asr_transcribe(tmp_path: Path) -> None:
    wav_path = tmp_path / "speech.wav"
    create_synthetic_wav(wav_path, duration_sec=4.0)

    asr = MockASR()
    result = asr.transcribe(wav_path, word_timestamps=True)

    assert result.duration >= 3.8
    assert result.language == "en"
    assert len(result.segments) > 0

    # Verify segments are ordered and valid
    last_end = 0.0
    for seg in result.segments:
        assert seg.start >= last_end - 0.01
        assert seg.end > seg.start
        assert len(seg.text) > 0
        last_end = seg.end


def test_mock_asr_forced_language_and_hint(tmp_path: Path) -> None:
    asr = MockASR()

    # Forced language
    wav_en = tmp_path / "test.wav"
    create_synthetic_wav(wav_en, duration_sec=2.0)
    res_hi = asr.transcribe(wav_en, forced_language="hi")
    assert res_hi.language == "hi"

    # Filename language hint
    wav_ta = tmp_path / "speech_ta.wav"
    create_synthetic_wav(wav_ta, duration_sec=2.0)
    res_hint = asr.transcribe(wav_ta)
    assert res_hint.language == "ta"


def test_audio_service_transcribe_and_rtf(tmp_path: Path) -> None:
    service = get_audio_service()
    wav_path = tmp_path / "rtf_test.wav"
    create_synthetic_wav(wav_path, duration_sec=2.5)

    result, timing_ms = service.transcribe(wav_path)
    assert result is not None
    assert len(result.text) > 0
    assert timing_ms >= 0


def test_audio_service_rejects_too_long_audio(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    service = get_audio_service()
    wav_path = tmp_path / "long.wav"
    create_synthetic_wav(wav_path, duration_sec=3.0)

    # Set threshold lower than audio file to test rejection
    monkeypatch.setattr(settings, "MAX_AUDIO_DURATION_SEC", 1)
    with pytest.raises(ValueError, match="exceeds maximum allowed limit"):
        service.transcribe(wav_path)
