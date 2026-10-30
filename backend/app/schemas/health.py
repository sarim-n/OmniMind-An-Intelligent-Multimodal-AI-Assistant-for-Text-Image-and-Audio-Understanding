"""Pydantic schemas for health and system status endpoints."""

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    """Health check response schema."""

    status: str = Field(default="ok", description="Current service health status")
    profile: str = Field(
        ..., description="Active hardware profile (cpu, gpu_low, gpu_mid, gpu_high)"
    )
    mock_models: bool = Field(..., description="Whether model inference is mocked")
    version: str = Field(..., description="Application version")
    timestamp: str = Field(..., description="UTC ISO timestamp of health check")
    models: dict[str, str] = Field(..., description="Active model identifiers for current profile")
    asr_settings: dict[str, str | int | bool] = Field(
        default_factory=dict, description="Active ASR configuration parameters"
    )
    vision_settings: dict[str, str | int | float | bool] = Field(
        default_factory=dict, description="Active Vision and VLM configuration parameters"
    )
