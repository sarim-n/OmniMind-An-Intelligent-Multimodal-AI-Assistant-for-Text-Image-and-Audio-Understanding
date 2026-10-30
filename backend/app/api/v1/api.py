"""API v1 router aggregation."""

from fastapi import APIRouter

from app.api.v1.endpoints import (
    audio,
    auth,
    conversations,
    health,
    images,
    jobs,
    reports,
    search,
)

api_router = APIRouter()
api_router.include_router(health.router, tags=["Health"])
api_router.include_router(auth.router, prefix="/auth", tags=["Authentication"])
api_router.include_router(conversations.router, prefix="/conversations", tags=["Conversations"])
api_router.include_router(audio.router, prefix="/audio", tags=["Audio"])
api_router.include_router(images.router, prefix="/images", tags=["Images"])
api_router.include_router(jobs.router, prefix="/jobs", tags=["Jobs"])
api_router.include_router(reports.router, prefix="/reports", tags=["Reports"])
api_router.include_router(search.router, prefix="/search", tags=["Search"])
