"""Unit tests for image preprocessing, safety verification, and quality analysis."""

from __future__ import annotations

import io

import numpy as np
import pytest
from PIL import Image, ImageDraw, ImageFilter

from app.core.config import settings
from app.services.image_preprocess import (
    enhance_image,
    preprocess_image,
    safe_load_image,
)


def make_test_image_bytes(
    width: int = 200,
    height: int = 200,
    color: tuple[int, int, int] = (100, 150, 200),
    draw_text: str | None = None,
    blur: bool = False,
    format: str = "JPEG",
) -> bytes:
    """Generate in-memory test image bytes using Pillow."""
    img = Image.new("RGB", (width, height), color)

    if draw_text:
        draw = ImageDraw.Draw(img)
        draw.text((10, 10), draw_text, fill=(255, 255, 255))

    if blur:
        img = img.filter(ImageFilter.GaussianBlur(radius=8))

    buf = io.BytesIO()
    img.save(buf, format=format)
    return buf.getvalue()


def test_preprocess_plain_image() -> None:
    img_bytes = make_test_image_bytes(
        width=240, height=180, color=(50, 120, 200), draw_text="OmniMind"
    )
    result = preprocess_image(img_bytes)

    assert result.original_size == (240, 180)
    assert result.processed_size == (240, 180)
    assert result.format == "JPEG"
    assert isinstance(result.quality, dict)
    assert "blur_score" in result.quality
    assert "brightness" in result.quality
    assert len(result.dominant_colors) > 0
    assert result.dominant_colors[0]["hex"].startswith("#")


def test_preprocess_blurry_image_warning() -> None:
    blurry_bytes = make_test_image_bytes(width=200, height=200, blur=True)
    result = preprocess_image(blurry_bytes)

    assert result.quality["is_blurry"] is True
    assert any("blurry" in w.lower() for w in result.warnings)


def test_preprocess_dark_image_warning() -> None:
    dark_bytes = make_test_image_bytes(width=200, height=200, color=(10, 10, 10))
    result = preprocess_image(dark_bytes)

    assert result.quality["is_dark"] is True
    assert any("dark" in w.lower() for w in result.warnings)


def test_preprocess_small_image_warning() -> None:
    small_bytes = make_test_image_bytes(width=80, height=80, color=(120, 120, 120))
    result = preprocess_image(small_bytes)

    assert result.quality["is_small"] is True
    assert any("small" in w.lower() for w in result.warnings)


def test_preprocess_exif_rotation_transposition() -> None:
    # Create image with EXIF orientation tag 6 (Rotate 90 CW)
    img = Image.new("RGB", (200, 100), (200, 100, 50))
    exif = img.getexif()
    exif[0x0112] = 6  # Orientation tag

    buf = io.BytesIO()
    img.save(buf, format="JPEG", exif=exif)
    buf.seek(0)

    loaded, _ = safe_load_image(buf)
    # Transposing orientation 6 swaps width and height
    assert loaded.size == (100, 200)


def test_preprocess_decompression_bomb_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    orig_pixels = Image.MAX_IMAGE_PIXELS
    monkeypatch.setattr(settings, "MAX_IMAGE_PIXELS", 5000)

    # 100x100 = 10,000 pixels (exceeds 5,000)
    oversized_bytes = make_test_image_bytes(width=100, height=100)

    try:
        with pytest.raises(ValueError, match="exceeds MAX_IMAGE_PIXELS"):
            preprocess_image(oversized_bytes)
    finally:
        Image.MAX_IMAGE_PIXELS = orig_pixels


def test_preprocess_clahe_enhancement() -> None:
    dark_img = Image.new("RGB", (150, 150), (25, 25, 25))
    enhanced = enhance_image(dark_img)

    assert enhanced.size == (150, 150)
    orig_brightness = float(np.mean(np.array(dark_img)))
    enh_brightness = float(np.mean(np.array(enhanced)))
    # CLAHE should increase brightness of very dark images
    assert enh_brightness >= orig_brightness
