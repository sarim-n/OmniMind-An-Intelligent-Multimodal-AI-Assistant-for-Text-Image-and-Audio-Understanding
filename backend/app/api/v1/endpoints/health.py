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
        orchestration_settings={
            "max_loaded_models": settings.MAX_LOADED_MODELS,
            "max_concurrent_inferences": settings.MAX_CONCURRENT_INFERENCES,
            "max_files_per_message": settings.MAX_FILES_PER_MESSAGE,
            "max_total_audio_duration_per_message_sec": settings.MAX_TOTAL_AUDIO_DURATION_PER_MESSAGE_SEC,
        },
        vault_settings={
            "vault_chroma_path": str(settings.VAULT_CHROMA_PATH),
            "search_default_top_k": settings.SEARCH_DEFAULT_TOP_K,
            "search_rerank_top_k": settings.SEARCH_RERANK_TOP_K,
            "meeting_min_duration_sec": settings.MEETING_MIN_DURATION_SEC,
            "hf_token_configured": bool(settings.HF_TOKEN),
        },
    )
