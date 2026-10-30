"""Pydantic schemas for computer vision, object detection, and visual QA."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class DetectedObject(BaseModel):
    """Detected visual object with bounding coordinates and classification confidence."""

    label: str = Field(..., description="Object category name")
    confidence: float = Field(..., description="Detection confidence score between 0.0 and 1.0")
    bbox: list[float] = Field(..., description="Bounding box in [x1, y1, x2, y2] format")


class DetectionResult(BaseModel):
    """Aggregated object detection output with classified objects and category counts."""

    objects: list[DetectedObject] = Field(default_factory=list)
    counts: dict[str, int] = Field(default_factory=dict)


class DominantColor(BaseModel):
    """Dominant image color representation."""

    hex: str = Field(..., description="Hexadecimal color string e.g. #FF0000")
    name: str = Field(..., description="Nearest human-readable color name")


class ImageQualityInfo(BaseModel):
    """Quantitative image quality and clarity metrics."""

    blur_score: float = Field(..., description="Laplacian variance sharpness score")
    brightness: float = Field(..., description="Average grayscale pixel intensity (0-255)")
    contrast: float = Field(..., description="Grayscale standard deviation intensity")
    is_blurry: bool = Field(default=False)
    is_dark: bool = Field(default=False)
    is_bright: bool = Field(default=False)
    low_contrast: bool = Field(default=False)
    is_small: bool = Field(default=False)


class ImageAnalysisRead(BaseModel):
    """Complete image analysis representation returned by API endpoints."""

    id: str
    attachment_id: str
    caption: str | None = None
    objects: list[DetectedObject] = Field(default_factory=list)
    counts: dict[str, int] = Field(default_factory=dict)
    ocr_text: str | None = None
    quality: dict[str, Any] = Field(default_factory=dict)
    dominant_colors: list[DominantColor] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    annotated_path: str | None = None
    timing_ms: float | None = None


class ImageAskRequest(BaseModel):
    """Visual Question Answering (VQA) request."""

    question: str = Field(..., min_length=1, description="Question about the image content")
    conversation_id: str | None = Field(
        default=None, description="Optional linked conversation for context memory"
    )


class ImageAskResponse(BaseModel):
    """Visual Question Answering response."""

    answer: str = Field(..., description="VLM answer to user question")
    timing_ms: float = Field(..., description="Latency of inference in milliseconds")
