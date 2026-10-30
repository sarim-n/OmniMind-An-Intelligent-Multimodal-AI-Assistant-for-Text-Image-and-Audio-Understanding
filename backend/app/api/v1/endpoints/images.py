"""Image analysis, Visual Question Answering (VQA), and visual artifact endpoints."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from starlette.datastructures import UploadFile as StarletteUploadFile

from app.core.logging import get_logger
from app.core.security import get_current_user
from app.db.session import get_db
from app.models.attachment import Attachment
from app.models.conversation import Conversation
from app.models.image_analysis import ImageAnalysis
from app.models.job import Job
from app.models.message import Message
from app.models.user import User
from app.schemas.job import JobRead
from app.schemas.vision import (
    DetectedObject,
    ImageAnalysisRead,
    ImageAskRequest,
    ImageAskResponse,
)
from app.services.job_service import get_job_service
from app.services.storage_service import get_storage_root, save_upload
from app.services.vision_service import get_vision_service
from app.workers.image_worker import execute_image_analysis_job

logger = get_logger(__name__)
router = APIRouter()


@router.post(
    "/analyze",
    response_model=JobRead,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Analyze image",
    description="Queue an asynchronous computer vision analysis job accepting either direct file upload or attachment ID.",
)
async def analyze_image(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Job:
    """Queue image understanding job with quality analysis, object detection, and VLM captioning."""
    content_type = request.headers.get("content-type", "")
    file: UploadFile | None = None
    attachment_id: str | None = None
    enhance: bool = False

    if "multipart/form-data" in content_type:
        form = await request.form()
        uploaded_file = form.get("file")
        if isinstance(uploaded_file, (UploadFile, StarletteUploadFile)):
            file = uploaded_file  # type: ignore[assignment]
        raw_att_id = form.get("attachment_id")
        if isinstance(raw_att_id, str) and raw_att_id.strip():
            attachment_id = raw_att_id.strip()
        raw_enhance = form.get("enhance")
        enhance = str(raw_enhance).lower() in ("true", "1", "yes")

    elif "application/json" in content_type:
        try:
            body = await request.json()
            attachment_id = body.get("attachment_id")
            enhance = bool(body.get("enhance", False))
        except Exception:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="Malformed JSON body"
            )

    # Resolve image attachment and disk file path
    attachment: Attachment | None = None
    if file is not None:
        attachment = await save_upload(
            file=file,
            kind="image",
            user_id=current_user.id,
            db=db,
        )
    elif attachment_id:
        attachment = (
            db.query(Attachment)
            .filter(Attachment.id == attachment_id, Attachment.user_id == current_user.id)
            .first()
        )
        if not attachment:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Attachment not found or unauthorized",
            )
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Either 'file' or 'attachment_id' must be provided.",
        )

    if attachment is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to resolve image attachment.",
        )

    # Validate image file on disk
    storage_root = get_storage_root()
    physical_path = storage_root / attachment.path
    if not physical_path.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Image file does not exist on storage disk",
        )

    # Register and dispatch background job
    job_service = get_job_service()
    job = job_service.create_job(
        user_id=current_user.id,
        job_type="image_analysis",
        db=db,
    )

    job_service.spawn_coroutine(
        execute_image_analysis_job(
            job_id=job.id,
            attachment_id=attachment.id,
            file_path=physical_path,
            user_id=current_user.id,
            enhance=enhance,
        )
    )

    return job


@router.get(
    "/{attachment_id}/analysis",
    response_model=ImageAnalysisRead,
    summary="Get image analysis",
    description="Retrieve previously generated visual analysis record for an image attachment.",
)
def get_image_analysis(
    attachment_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ImageAnalysisRead:
    """Retrieve structured analysis results ensuring strict user ownership isolation."""
    attachment = (
        db.query(Attachment)
        .filter(Attachment.id == attachment_id, Attachment.user_id == current_user.id)
        .first()
    )
    if not attachment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Image attachment not found or unauthorized",
        )

    analysis = db.query(ImageAnalysis).filter(ImageAnalysis.attachment_id == attachment_id).first()
    if not analysis:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No visual analysis found for this image attachment",
        )

    meta = analysis.metadata_ or {}

    return ImageAnalysisRead(
        id=analysis.id,
        attachment_id=analysis.attachment_id,
        caption=analysis.caption,
        objects=[DetectedObject.model_validate(obj) for obj in (analysis.objects or [])],
        counts=meta.get("counts", {}),
        ocr_text=analysis.ocr_text,
        quality=meta.get("quality", {}),
        dominant_colors=meta.get("dominant_colors", []),
        warnings=meta.get("warnings", []),
        annotated_path=meta.get("annotated_path"),
        timing_ms=meta.get("timing_ms"),
    )


@router.post(
    "/{attachment_id}/ask",
    response_model=ImageAskResponse,
    summary="Ask a question about an image (VQA)",
    description="Visual Question Answering using VLM with optional conversation history context.",
)
async def ask_image_question(
    attachment_id: str,
    body: ImageAskRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ImageAskResponse:
    """Answer question regarding image content with user-scoped isolation and optional history."""
    attachment = (
        db.query(Attachment)
        .filter(Attachment.id == attachment_id, Attachment.user_id == current_user.id)
        .first()
    )
    if not attachment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Image attachment not found or unauthorized",
        )

    storage_root = get_storage_root()
    physical_path = storage_root / attachment.path
    if not physical_path.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Image file does not exist on storage disk",
        )

    # Optional conversation history lookup
    history: list[dict[str, Any]] | None = None
    if body.conversation_id:
        conv = (
            db.query(Conversation)
            .filter(
                Conversation.id == body.conversation_id,
                Conversation.user_id == current_user.id,
            )
            .first()
        )
        if not conv:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Linked conversation not found or unauthorized",
            )

        messages = (
            db.query(Message)
            .filter(Message.conversation_id == body.conversation_id)
            .order_by(Message.created_at.asc())
            .all()
        )
        history = [{"role": msg.role, "content": msg.content} for msg in messages]

    vision_service = get_vision_service()
    answer_text, timing_ms = vision_service.answer(
        image=physical_path,
        question=body.question,
        history=history,
    )

    return ImageAskResponse(answer=answer_text, timing_ms=timing_ms)


@router.get(
    "/{attachment_id}/annotated",
    summary="Serve annotated detection image",
    description="Return OpenCV-annotated derived image with bounding boxes for the owner.",
)
def get_annotated_image(
    attachment_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> FileResponse:
    """Serve annotated image artifact ensuring strict owner authentication."""
    attachment = (
        db.query(Attachment)
        .filter(Attachment.id == attachment_id, Attachment.user_id == current_user.id)
        .first()
    )
    if not attachment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Image attachment not found or unauthorized",
        )

    analysis = db.query(ImageAnalysis).filter(ImageAnalysis.attachment_id == attachment_id).first()
    if not analysis or not analysis.metadata_ or not analysis.metadata_.get("annotated_path"):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Annotated image has not been generated for this attachment",
        )

    storage_root = get_storage_root()
    annotated_file = storage_root / analysis.metadata_["annotated_path"]
    if not annotated_file.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Annotated image file not found on storage disk",
        )

    return FileResponse(
        path=str(annotated_file),
        media_type="image/jpeg",
        filename=f"{attachment_id}_annotated.jpg",
    )


@router.get(
    "/{attachment_id}/file",
    summary="Serve original image file",
    description="Return original uploaded image file with ownership verification.",
)
def get_image_file(
    attachment_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> FileResponse:
    """Serve original image file ensuring strict owner authentication."""
    attachment = (
        db.query(Attachment)
        .filter(Attachment.id == attachment_id, Attachment.user_id == current_user.id)
        .first()
    )
    if not attachment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Image attachment not found or unauthorized",
        )

    storage_root = get_storage_root()
    physical_path = storage_root / attachment.path
    if not physical_path.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Image file not found on storage disk",
        )

    media_type = attachment.mime or "image/jpeg"
    orig_name = (
        (attachment.metadata_ or {}).get("original_filename")
        or Path(attachment.path).name
        or f"{attachment_id}.jpg"
    )
    return FileResponse(
        path=str(physical_path),
        media_type=media_type,
        filename=orig_name,
    )
