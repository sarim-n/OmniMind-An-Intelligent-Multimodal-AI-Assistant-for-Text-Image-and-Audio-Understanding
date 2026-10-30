"""Pydantic schemas for structured reports and PDF export."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class ReportSection(BaseModel):
    """Section of a structured report."""

    heading: str
    body: str
    bullet_points: list[str] = Field(default_factory=list)


class ReportAudioFinding(BaseModel):
    """Factual and narrative findings from an audio asset."""

    file: str
    language: str = "en"
    duration: float = 0.0
    summary: str = ""
    key_points: list[str] = Field(default_factory=list)
    action_items: list[dict[str, Any]] = Field(default_factory=list)
    decisions: list[str] = Field(default_factory=list)
    timeline: list[dict[str, Any]] = Field(default_factory=list)


class ReportImageFinding(BaseModel):
    """Factual and visual findings from an image asset."""

    file: str
    caption: str = ""
    objects: list[dict[str, Any]] = Field(default_factory=list)
    extracted_text: str | None = None
    quality_warnings: list[str] = Field(default_factory=list)
    qa_highlights: list[dict[str, Any]] = Field(default_factory=list)


class ReportAppendix(BaseModel):
    """Metadata, source attachments, active models, and telemetry metrics."""

    sources: list[str] = Field(default_factory=list)
    models_used: dict[str, str] = Field(default_factory=dict)
    processing_metrics: dict[str, Any] = Field(default_factory=dict)


class ReportSchema(BaseModel):
    """Complete structured multimodal intelligence report schema."""

    title: str
    generated_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    language: str = "en"
    executive_summary: str = ""
    sections: list[ReportSection] = Field(default_factory=list)
    audio_findings: list[ReportAudioFinding] = Field(default_factory=list)
    image_findings: list[ReportImageFinding] = Field(default_factory=list)
    cross_modal_observations: list[str] = Field(default_factory=list)
    conclusions: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)
    appendix: ReportAppendix = Field(default_factory=ReportAppendix)
    errors: list[str] = Field(default_factory=list)


class ReportOptions(BaseModel):
    """User-specified parameters for report generation."""

    sections: list[str] | None = None
    language: str = "en"
    length: Literal["brief", "standard", "detailed"] = "standard"
    include_images: bool = True
    include_metrics: bool = True


class ReportCreateRequest(BaseModel):
    """Request payload to initiate report generation."""

    conversation_id: str
    options: ReportOptions = Field(default_factory=ReportOptions)


class ReportResponse(BaseModel):
    """Detailed response schema for an individual report."""

    id: str
    conversation_id: str
    title: str
    created_at: datetime
    pdf_path: str | None = None
    content: ReportSchema


class ReportListItem(BaseModel):
    """Compact summary schema for report listings."""

    id: str
    conversation_id: str
    title: str
    created_at: datetime
    pdf_path: str | None = None


class ReportCreateResponse(BaseModel):
    """Response returned upon submitting report generation job."""

    job_id: str
    status: str = "pending"
    report_id: str | None = None
