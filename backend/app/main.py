"""Main FastAPI application entry point."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import UTC, datetime

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.api import api_router
from app.core.config import settings
from app.core.logging import get_logger, setup_logging
from app.schemas.health import HealthResponse

# Initialize structured logging
setup_logging()
logger = get_logger("app.main")


def mark_orphan_jobs_failed() -> int:
    """Mark any jobs left in 'running' state on server startup as failed."""
    import app.db.session
    from app.models.job import Job

    try:
        with app.db.session.SessionLocal() as db:
            orphan_jobs = db.query(Job).filter(Job.status == "running").all()
            count = len(orphan_jobs)
            for j in orphan_jobs:
                j.status = "failed"
                j.error = "Job interrupted by server shutdown/restart"
                j.updated_at = datetime.now(UTC)
            if count > 0:
                db.commit()
                logger.info("Marked orphan jobs as failed", count=count)
            return count
    except Exception as e:
        logger.warning("Failed to check orphan jobs on startup", error=str(e))
        return 0


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan context manager for startup and shutdown tasks."""
    logger.info(
        "Application startup",
        profile=settings.PROFILE,
        mock_models=settings.MOCK_MODELS,
        version=settings.VERSION,
        environment=settings.ENVIRONMENT,
    )
    mark_orphan_jobs_failed()
    yield
    logger.info("Application shutdown")


app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    description="Backend API for the Intelligent Multimodal AI Assistant",
    lifespan=lifespan,
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get(
    "/health",
    response_model=HealthResponse,
    tags=["Health"],
    summary="Health check",
    description="Returns root health status, profile, mock status, and configured models.",
)
async def health_check() -> HealthResponse:
    """Root health check endpoint."""
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


# Include API v1 router
app.include_router(api_router, prefix=settings.API_V1_PREFIX)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
