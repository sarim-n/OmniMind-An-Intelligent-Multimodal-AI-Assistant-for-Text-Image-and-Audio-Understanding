"""Image preprocessing, safety validation, quality analysis, and metadata extraction.

Pure OpenCV and Pillow operations; strictly no heavy ML models required.
"""

from __future__ import annotations

import io
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import cv2
import numpy as np
from PIL import Image, ImageOps
from sklearn.cluster import KMeans

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

# Standard color palette for mapping RGB centroid clusters to human-readable names
COLOR_PALETTE: dict[str, tuple[int, int, int]] = {
    "Black": (15, 15, 15),
    "White": (245, 245, 245),
    "Gray": (128, 128, 128),
    "Red": (220, 30, 30),
    "Orange": (255, 140, 20),
    "Yellow": (250, 215, 30),
    "Green": (34, 150, 34),
    "Blue": (30, 130, 240),
    "Navy": (10, 25, 100),
    "Purple": (130, 30, 140),
    "Pink": (255, 105, 180),
    "Brown": (140, 70, 25),
    "Cyan": (0, 200, 210),
}


def _rgb_to_color_name(r: int, g: int, b: int) -> str:
    """Find the closest human-readable color name by Euclidean distance in RGB space."""
    best_name = "Unknown"
    min_dist = float("inf")

    for name, (cr, cg, cb) in COLOR_PALETTE.items():
        dist = math.sqrt((r - cr) ** 2 + (g - cg) ** 2 + (b - cb) ** 2)
        if dist < min_dist:
            min_dist = dist
            best_name = name

    return best_name


@dataclass
class PreprocessedImage:
    """Output of the image preprocessing pipeline."""

    image: Image.Image
    original_size: tuple[int, int]
    processed_size: tuple[int, int]
    format: str
    quality: dict[str, Any]
    dominant_colors: list[dict[str, str]]
    warnings: list[str] = field(default_factory=list)


def safe_load_image(source: Path | str | bytes | io.BytesIO) -> tuple[Image.Image, str]:
    """Safely open an image, guard against decompression bombs, fix EXIF rotation, and convert to RGB.

    Returns (PIL.Image, detected_format).
    """
    # Configure Pillow decompression bomb guard limit
    Image.MAX_IMAGE_PIXELS = settings.MAX_IMAGE_PIXELS

    raw_img: Image.Image
    try:
        if isinstance(source, (str, Path)):
            path = Path(source).resolve()
            if not path.is_file():
                raise FileNotFoundError(f"Image file does not exist: {path}")
            raw_img = Image.open(str(path))
        elif isinstance(source, bytes):
            raw_img = Image.open(io.BytesIO(source))
        elif isinstance(source, io.BytesIO):
            raw_img = Image.open(source)
        else:
            raise TypeError(f"Unsupported image input type: {type(source)}")
    except Image.DecompressionBombError as e:
        raise ValueError(
            f"Image exceeds maximum permitted pixel count of {settings.MAX_IMAGE_PIXELS}: {e}"
        ) from e

    # Explicit pixel count check in case Pillow check was bypassed or deferred
    total_pixels = raw_img.width * raw_img.height
    if total_pixels > settings.MAX_IMAGE_PIXELS:
        raise ValueError(
            f"Image resolution ({raw_img.width}x{raw_img.height} = {total_pixels} pixels) "
            f"exceeds MAX_IMAGE_PIXELS threshold ({settings.MAX_IMAGE_PIXELS})"
        )

    img_format = raw_img.format or "JPEG"

    # EXIF-aware orientation transposition
    try:
        oriented_img = ImageOps.exif_transpose(raw_img)
        if oriented_img is not None:
            raw_img = oriented_img
    except Exception as e:
        logger.debug("Failed EXIF orientation transpose, using unoriented image", error=str(e))

    # Convert to RGB mode cleanly (handling transparency / paletted / CMYK formats)
    if raw_img.mode in ("RGBA", "LA") or (raw_img.mode == "P" and "transparency" in raw_img.info):
        converted = raw_img.convert("RGBA")
        background = Image.new("RGBA", converted.size, (255, 255, 255, 255))
        composite = Image.alpha_composite(background, converted)
        rgb_img = composite.convert("RGB")
    elif raw_img.mode != "RGB":
        rgb_img = raw_img.convert("RGB")
    else:
        rgb_img = raw_img.copy()

    return rgb_img, img_format


def resize_preserving_aspect(
    image: Image.Image,
    max_side: int = settings.VLM_MAX_IMAGE_SIDE,
) -> Image.Image:
    """Resize image so its longest dimension does not exceed max_side, preserving aspect ratio."""
    width, height = image.size
    longest = max(width, height)

    if longest <= max_side:
        return image

    scale = max_side / float(longest)
    new_w = max(1, round(width * scale))
    new_h = max(1, round(height * scale))

    return image.resize((new_w, new_h), Image.Resampling.LANCZOS)


def check_image_quality(image: Image.Image) -> tuple[dict[str, Any], list[str]]:
    """Assess visual quality metrics: blur (Laplacian variance), brightness, contrast, dimensions.

    Returns (quality_dict, warnings_list).
    """
    width, height = image.size
    warnings: list[str] = []

    # Convert PIL Image to OpenCV grayscale numpy array
    rgb_arr = np.array(image)
    gray = cv2.cvtColor(rgb_arr, cv2.COLOR_RGB2GRAY)

    # 1. Blur Score via Laplacian Variance
    laplacian_var = float(cv2.Laplacian(gray, cv2.CV_64F).var())
    is_blurry = laplacian_var < 100.0
    if is_blurry:
        warnings.append(
            f"Image appears blurry (sharpness score {laplacian_var:.1f} is below 100.0)"
        )

    # 2. Brightness via Mean Pixel Intensity
    brightness = float(np.mean(gray))
    is_dark = brightness < 40.0
    is_bright = brightness > 220.0
    if is_dark:
        warnings.append(f"Image is too dark (brightness {brightness:.1f} is below 40.0)")
    elif is_bright:
        warnings.append(f"Image is overexposed (brightness {brightness:.1f} is above 220.0)")

    # 3. Contrast via Standard Deviation
    contrast = float(np.std(gray))
    low_contrast = contrast < 30.0
    if low_contrast:
        warnings.append(f"Image has low contrast (standard deviation {contrast:.1f} is below 30.0)")

    # 4. Dimension Resolution Checks
    is_small = width < 100 or height < 100
    if is_small:
        warnings.append(f"Image resolution is very small ({width}x{height} is under 100px)")

    quality_dict: dict[str, Any] = {
        "blur_score": round(laplacian_var, 2),
        "brightness": round(brightness, 2),
        "contrast": round(contrast, 2),
        "is_blurry": is_blurry,
        "is_dark": is_dark,
        "is_bright": is_bright,
        "low_contrast": low_contrast,
        "is_small": is_small,
    }

    return quality_dict, warnings


def enhance_image(image: Image.Image) -> Image.Image:
    """Apply light Contrast Limited Adaptive Histogram Equalization (CLAHE) in LAB color space."""
    rgb_arr = np.array(image)
    lab = cv2.cvtColor(rgb_arr, cv2.COLOR_RGB2LAB)
    l_channel, a_channel, b_channel = cv2.split(lab)

    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    enhanced_l = clahe.apply(l_channel)

    enhanced_lab = cv2.merge((enhanced_l, a_channel, b_channel))
    enhanced_rgb = cv2.cvtColor(enhanced_lab, cv2.COLOR_LAB2RGB)
    return Image.fromarray(enhanced_rgb)


def extract_dominant_colors(image: Image.Image, k: int = 3) -> list[dict[str, str]]:
    """Extract top-k dominant colors using k-means clustering.

    Returns list of dicts with {"hex": "#RRGGBB", "name": "ColorName"}.
    """
    # Downscale thumbnail for fast deterministic clustering
    thumb = image.resize((80, 80), Image.Resampling.BILINEAR)
    pixels = np.array(thumb).reshape(-1, 3).astype(np.float32)

    if len(pixels) == 0:
        return [{"hex": "#000000", "name": "Black"}]

    unique_pixels = np.unique(pixels, axis=0)
    n_clusters = max(1, min(k, len(unique_pixels)))
    kmeans = KMeans(n_clusters=n_clusters, n_init=3, random_state=42)
    labels = kmeans.fit_predict(pixels)
    centers = kmeans.cluster_centers_

    # Sort clusters by frequency
    counts = np.bincount(labels, minlength=n_clusters)
    sorted_indices = np.argsort(-counts)

    results: list[dict[str, str]] = []
    for idx in sorted_indices:
        r, g, b = [int(np.clip(c, 0, 255)) for c in centers[idx]]
        hex_code = f"#{r:02x}{g:02x}{b:02x}".upper()
        name = _rgb_to_color_name(r, g, b)
        results.append({"hex": hex_code, "name": name})

    return results


def preprocess_image(
    source: Path | str | bytes | io.BytesIO,
    enhance: bool = False,
    max_side: int = settings.VLM_MAX_IMAGE_SIDE,
) -> PreprocessedImage:
    """Full preprocessing pipeline: safe load -> quality metrics -> colors -> resize -> optional CLAHE."""
    rgb_img, img_format = safe_load_image(source)
    orig_size = rgb_img.size

    # Run quality metrics on original dimensions
    quality, warnings = check_image_quality(rgb_img)

    # Extract dominant colors
    dominant_colors = extract_dominant_colors(rgb_img, k=3)

    # Apply optional CLAHE enhancement if requested
    if enhance:
        rgb_img = enhance_image(rgb_img)

    # Resize preserving aspect ratio for downstream VLM & detector models
    resized_img = resize_preserving_aspect(rgb_img, max_side=max_side)
    processed_size = resized_img.size

    return PreprocessedImage(
        image=resized_img,
        original_size=orig_size,
        processed_size=processed_size,
        format=img_format,
        quality=quality,
        dominant_colors=dominant_colors,
        warnings=warnings,
    )
