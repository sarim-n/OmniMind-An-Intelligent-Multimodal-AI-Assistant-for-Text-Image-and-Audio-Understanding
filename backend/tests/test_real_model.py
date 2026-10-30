"""Opt-in smoke test for real model loading, marked as slow."""

import os
from pathlib import Path

import pytest

from app.core.config import settings
from app.services.embedding_service import EmbeddingService


@pytest.mark.slow
def test_real_embedding_model_load_and_inference() -> None:
    """Verify loading real weights and computing embeddings when opt-in enabled."""
    if settings.MOCK_MODELS and os.getenv("RUN_REAL_MODEL_TESTS", "0") != "1":
        pytest.skip(
            "MOCK_MODELS=true is set; set RUN_REAL_MODEL_TESTS=1 to run real model smoke test."
        )

    # Temporarily instantiate real embedding service without mock
    orig_mock = settings.MOCK_MODELS
    try:
        settings.MOCK_MODELS = False
        service = EmbeddingService()
        service.load()
        assert service._loaded is True
        assert service.device in ("cpu", "cuda")

        vec, timing_ms = service.embed_query("OmniMind verification query")
        assert len(vec) == service.dim
        assert timing_ms > 0
    finally:
        settings.MOCK_MODELS = orig_mock


@pytest.mark.slow
def test_real_faster_whisper_transcribe(tmp_path: Path) -> None:
    """Verify loading real faster-whisper base model when opt-in enabled."""
    if settings.MOCK_MODELS and os.getenv("RUN_REAL_MODEL_TESTS", "0") != "1":
        pytest.skip(
            "MOCK_MODELS=true is set; set RUN_REAL_MODEL_TESTS=1 to run real model smoke test."
        )

    from app.services.audio_service import AudioService
    from tests.test_audio_service import create_synthetic_wav

    wav_file = tmp_path / "test_clip.wav"
    create_synthetic_wav(wav_file, duration_sec=2.0)

    orig_mock = settings.MOCK_MODELS
    try:
        settings.MOCK_MODELS = False
        service = AudioService()
        service.load()
        assert service._loaded is True

        result, timing_ms = service.transcribe(wav_file)
        assert result is not None
        assert result.duration >= 1.5
        assert timing_ms > 0
    finally:
        settings.MOCK_MODELS = orig_mock


@pytest.mark.slow
def test_real_detector_load_and_detect() -> None:
    """Verify loading real RT-DETR detector on a small image when opt-in enabled."""
    if settings.MOCK_MODELS and os.getenv("RUN_REAL_MODEL_TESTS", "0") != "1":
        pytest.skip(
            "MOCK_MODELS=true is set; set RUN_REAL_MODEL_TESTS=1 to run real model smoke test."
        )

    from PIL import Image

    from app.services.detector_service import DetectorService

    img = Image.new("RGB", (200, 200), (120, 120, 120))
    orig_mock = settings.MOCK_MODELS
    try:
        settings.MOCK_MODELS = False
        service = DetectorService()
        service.load()
        assert service._loaded is True

        result, timing_ms = service.detect(img)
        assert result is not None
        assert timing_ms >= 0
    finally:
        settings.MOCK_MODELS = orig_mock


@pytest.mark.slow
def test_real_vlm_load_and_describe() -> None:
    """Verify loading real VLM checkpoint on a small image when opt-in enabled."""
    if settings.MOCK_MODELS and os.getenv("RUN_REAL_MODEL_TESTS", "0") != "1":
        pytest.skip(
            "MOCK_MODELS=true is set; set RUN_REAL_MODEL_TESTS=1 to run real model smoke test."
        )

    from PIL import Image

    from app.services.vision_service import VisionService

    img = Image.new("RGB", (100, 100), (150, 150, 150))
    orig_mock = settings.MOCK_MODELS
    try:
        settings.MOCK_MODELS = False
        service = VisionService()
        service.load()
        assert service._loaded is True

        caption, timing_ms = service.describe(img, detail_level="brief")
        assert len(caption) > 0
        assert timing_ms >= 0
    finally:
        settings.MOCK_MODELS = orig_mock
