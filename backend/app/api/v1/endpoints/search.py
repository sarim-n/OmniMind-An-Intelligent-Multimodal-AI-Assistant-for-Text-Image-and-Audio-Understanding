"""Knowledge Vault REST API endpoints for cross-modal search, visual queries, reindexing, and stats."""

from __future__ import annotations

import asyncio
import time
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.core.security import get_current_user
from app.db.session import SessionLocal, get_db
from app.models.user import User
from app.schemas.search import (
    ReindexResponse,
    SearchRequest,
    SearchResponse,
    SearchStats,
)
from app.services.job_service import get_job_service
from app.services.search_service import get_search_service
from app.services.storage_service import validate_media_upload

logger = get_logger(__name__)

router = APIRouter()


async def _run_reindex_job(job_id: str, user_id: str) -> None:
    """Execute background vault reindexing job."""
    job_service = get_job_service()
    job_service.update_job_status(job_id=job_id, status="running", progress=0.1)

    db_session = SessionLocal()
    try:
        search_service = get_search_service()
        indexed_count = search_service.reindex_user(user_id, db_session)
        job_service.update_job_status(
            job_id=job_id,
            status="done",
            progress=1.0,
            result={"indexed_items": indexed_count},
        )
    except Exception as e:
        logger.error("Reindex background job failed", job_id=job_id, error=str(e))
        job_service.update_job_status(job_id=job_id, status="failed", progress=1.0, error=str(e))
    finally:
        db_session.close()


@router.post(
    "",
    response_model=SearchResponse,
    summary="Cross-modal semantic search",
    description="Search Knowledge Vault text, audio transcripts, and image analyses with reciprocal rank fusion.",
)
async def search_vault(
    request: SearchRequest,
    current_user: User = Depends(get_current_user),
) -> SearchResponse:
    """Execute natural language search query across multimodal Knowledge Vault."""
    start_time = time.perf_counter()
    search_service = get_search_service()

    results = search_service.search_vault(
        query=request.query,
        user_id=current_user.id,
        modalities=request.modalities,
        conversation_id=request.conversation_id,
        top_k=request.top_k,
        rerank=request.rerank,
        date_from=request.date_from,
        date_to=request.date_to,
        language=request.language,
    )

    latency_ms = (time.perf_counter() - start_time) * 1000.0
    return SearchResponse(
        query=request.query,
        total_results=len(results),
        results=results,
        latency_ms=round(latency_ms, 2),
    )


@router.post(
    "/by-image",
    response_model=SearchResponse,
    summary="Search by image",
    description="Retrieve visually similar images and associated contextual transcripts using SigLIP image embeddings.",
)
async def search_by_image(
    file: Annotated[UploadFile, File(description="Query image file")],
    top_k: Annotated[int, Form()] = 10,
    rerank: Annotated[bool, Form()] = False,
    conversation_id: Annotated[str | None, Form()] = None,
    current_user: User = Depends(get_current_user),
) -> SearchResponse:
    """Search Knowledge Vault using an uploaded reference image."""
    start_time = time.perf_counter()
    # Sniff and validate uploaded file
    try:
        content_bytes = await file.read()
        validate_media_upload(file.filename or "query.png", content_bytes, allowed_type="image")
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid image file: {e!s}",
        ) from e

    search_service = get_search_service()
    results = search_service.search_by_image(
        image_input=content_bytes,
        user_id=current_user.id,
        conversation_id=conversation_id,
        top_k=top_k,
        rerank=rerank,
        filename=file.filename,
    )

    latency_ms = (time.perf_counter() - start_time) * 1000.0
    return SearchResponse(
        query=file.filename or "image_query",
        total_results=len(results),
        results=results,
        latency_ms=round(latency_ms, 2),
    )


@router.post(
    "/reindex",
    response_model=ReindexResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Reindex Knowledge Vault",
    description="Triggers an asynchronous background job to rebuild the current user's Knowledge Vault index.",
)
async def reindex_vault(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ReindexResponse:
    """Register and trigger background job to re-index all user conversations and media."""
    job_service = get_job_service()
    job = job_service.create_job(user_id=current_user.id, job_type="vault_reindex", db=db)

    asyncio.create_task(_run_reindex_job(job.id, current_user.id))

    return ReindexResponse(
        job_id=job.id,
        status="queued",
        message="Knowledge Vault re-indexing job queued successfully",
    )


@router.get(
    "/stats",
    response_model=SearchStats,
    summary="Knowledge Vault stats",
    description="Retrieve counts of indexed items in Knowledge Vault categorized by modality.",
)
def get_vault_stats(
    current_user: User = Depends(get_current_user),
) -> SearchStats:
    """Get statistics on indexed items in Knowledge Vault for the authenticated user."""
    search_service = get_search_service()
    return search_service.get_stats(current_user.id)
