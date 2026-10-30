"""Unit tests for DetectorService and RT-DETR visual detection."""

from __future__ import annotations

import tempfile
from pathlib import Path

from PIL import Image

from app.schemas.vision import DetectionResult
from app.services.detector_service import MockDetector, get_detector_service


def test_mock_detector_boxes_and_counts() -> None:
    detector = MockDetector()
    img = Image.new("RGB", (320, 240), (180, 180, 180))

    result = detector.detect(img)
    assert isinstance(result, DetectionResult)
    assert len(result.objects) >= 2
    assert "person" in result.counts
    assert "laptop" in result.counts

    for obj in result.objects:
        assert len(obj.bbox) == 4
        x1, y1, x2, y2 = obj.bbox
        assert 0.0 <= x1 < x2 <= 320.0
        assert 0.0 <= y1 < y2 <= 240.0
        assert 0.0 <= obj.confidence <= 1.0


def test_detector_service_draw_annotations() -> None:
    service = get_detector_service()
    img = Image.new("RGB", (250, 250), (220, 220, 220))

    result, latency = service.detect(img)
    assert len(result.objects) > 0
    assert latency >= 0.0

    with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as f:
        tmp_path = Path(f.name)

    try:
        annotated_path = service.draw_annotations(img, result.objects, tmp_path)
        assert annotated_path.is_file()
        assert annotated_path.stat().st_size > 0

        # Verify output is valid image
        with Image.open(str(annotated_path)) as loaded:
            assert loaded.size == (250, 250)
    finally:
        if tmp_path.exists():
            tmp_path.unlink()


def test_detector_service_infer_unified_method() -> None:
    service = get_detector_service()
    img = Image.new("RGB", (150, 150), (50, 50, 50))
    res, timing_ms = service.infer(img)

    assert isinstance(res, DetectionResult)
    assert timing_ms >= 0.0
