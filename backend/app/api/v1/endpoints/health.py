"""Health check endpoint."""

from datetime import UTC, datetime

from fastapi import APIRouter

from app.core.config import settings
from app.schemas.health import HealthResponse

router = APIRouter()


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Health check",
    description="Returns the health status, hardware profile, model configuration, and version.",
)
async def health_check() -> HealthResponse:
    """Check system health status and active configuration."""
    return HealthResponse(
        status="ok",
        profile=settings.PROFILE,
        mock_models=settings.MOCK_MODELS,
        version=settings.VERSION,
        timestamp=datetime.now(UTC).isoformat(),
        models=settings.active_models,
        asr_settings={
            "model": settings.effective_asr_model,
            "compute_type": settings.ASR_COMPUTE_TYPE,
            "beam_size": settings.ASR_BEAM_SIZE,
            "vad_filter": settings.ASR_VAD_FILTER,
            "max_duration_sec": settings.MAX_AUDIO_DURATION_SEC,
        },
        vision_settings={
            "vlm_model": settings.effective_vlm_model,
            "detector_model": settings.effective_detector_model,
            "vlm_max_new_tokens": settings.VLM_MAX_NEW_TOKENS,
            "vlm_max_image_side": settings.VLM_MAX_IMAGE_SIDE,
            "detector_threshold": settings.DETECTOR_THRESHOLD,
            "max_image_pixels": settings.MAX_IMAGE_PIXELS,
        },
    )
