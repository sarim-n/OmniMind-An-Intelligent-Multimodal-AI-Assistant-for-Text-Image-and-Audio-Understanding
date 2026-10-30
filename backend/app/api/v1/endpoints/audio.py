"""Audio transcription, transcript retrieval, and insights endpoints."""

from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, status
from sqlalchemy.orm import Session
from starlette.datastructures import UploadFile as StarletteUploadFile

from app.core.config import settings
from app.core.logging import get_logger
from app.core.security import get_current_user
from app.db.session import get_db
from app.models.attachment import Attachment
from app.models.job import Job
from app.models.transcript import Transcript
from app.models.user import User
from app.schemas.audio import (
    AudioInsights,
    AudioInsightsRequest,
    MeetingInsights,
    TranscriptRead,
)
from app.schemas.job import JobRead
from app.services.audio_insights import get_audio_insights_service
from app.services.audio_service import probe_audio_duration_seconds
from app.services.job_service import get_job_service
from app.services.storage_service import get_storage_root, save_upload
from app.workers.audio_worker import execute_transcription_job

logger = get_logger(__name__)
router = APIRouter()


@router.post(
    "/transcribe",
    response_model=JobRead,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Transcribe audio file or attachment",
    description="Queue an asynchronous audio transcription job accepting either a direct file upload or attachment ID.",
)
async def transcribe_audio(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Job:
    """Queue transcription job with language detection or forced language and translation options."""
    content_type = request.headers.get("content-type", "")
    file: UploadFile | None = None
    attachment_id: str | None = None
    language: str | None = None
    translate: bool = False
    word_timestamps: bool = False

    if "multipart/form-data" in content_type:
        form = await request.form()
        uploaded_file = form.get("file")
        if isinstance(uploaded_file, (UploadFile, StarletteUploadFile)):
            file = uploaded_file  # type: ignore[assignment]
        raw_att_id = form.get("attachment_id")
        if isinstance(raw_att_id, str) and raw_att_id.strip():
            attachment_id = raw_att_id.strip()

        raw_lang = form.get("language")
        if isinstance(raw_lang, str) and raw_lang.strip():
            language = raw_lang.strip()

        raw_trans = form.get("translate")
        translate = str(raw_trans).lower() in ("true", "1", "yes")

        raw_wt = form.get("word_timestamps")
        word_timestamps = str(raw_wt).lower() in ("true", "1", "yes")

    elif "application/json" in content_type:
        try:
            body = await request.json()
            attachment_id = body.get("attachment_id")
            language = body.get("language")
            translate = bool(body.get("translate", False))
            word_timestamps = bool(body.get("word_timestamps", False))
        except Exception:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="Malformed JSON body"
            )

    # Resolve audio attachment and disk file path
    attachment: Attachment | None = None
    if file is not None:
        attachment = await save_upload(
            file=file,
            kind="audio",
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
            detail="Failed to resolve audio attachment.",
        )

    # Validate audio file on disk
    storage_root = get_storage_root()
    physical_path = storage_root / attachment.path
    if not physical_path.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Audio file does not exist on storage disk",
        )

    # Enforce maximum audio duration limit
    duration_sec = probe_audio_duration_seconds(physical_path)
    if duration_sec > settings.MAX_AUDIO_DURATION_SEC:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Audio duration ({duration_sec:.1f}s) exceeds maximum allowed limit "
                f"of {settings.MAX_AUDIO_DURATION_SEC}s"
            ),
        )

    # Register and dispatch background job
    job_service = get_job_service()
    job = job_service.create_job(
        user_id=current_user.id,
        job_type="audio_transcription",
        db=db,
    )

    job_service.spawn_coroutine(
        execute_transcription_job(
            job_id=job.id,
            attachment_id=attachment.id,
            file_path=physical_path,
            language=language,
            translate=translate,
            word_timestamps=word_timestamps,
        )
    )

    return job


@router.get(
    "/{attachment_id}/transcript",
    response_model=TranscriptRead,
    summary="Get audio transcript",
    description="Retrieve previously generated transcription record for an audio attachment.",
)
def get_audio_transcript(
    attachment_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Transcript:
    """Fetch transcript strictly scoped to user's attachment."""
    attachment = (
        db.query(Attachment)
        .filter(Attachment.id == attachment_id, Attachment.user_id == current_user.id)
        .first()
    )
    if not attachment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Attachment not found",
        )

    transcript = db.query(Transcript).filter(Transcript.attachment_id == attachment_id).first()
    if not transcript:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Transcript not found for this attachment",
        )

    return transcript


@router.post(
    "/{attachment_id}/insights",
    response_model=AudioInsights,
    summary="Generate insights from audio transcript",
    description="Run structured LLM analysis (summaries, action items, topics, entities) on an audio transcript.",
)
def generate_audio_insights(
    attachment_id: str,
    payload: AudioInsightsRequest | None = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AudioInsights:
    """Analyze transcript, persist summaries and structured insights, and return results."""
    attachment = (
        db.query(Attachment)
        .filter(Attachment.id == attachment_id, Attachment.user_id == current_user.id)
        .first()
    )
    if not attachment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Attachment not found",
        )

    transcript = db.query(Transcript).filter(Transcript.attachment_id == attachment_id).first()
    if not transcript:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Transcript not found for this attachment",
        )

    insights_service = get_audio_insights_service()
    target_lang = payload.output_language if payload else None
    insights = insights_service.extract_insights(transcript.text, output_language=target_lang)

    # Persist summary and structured insights back to transcript record
    transcript.summary = insights.short_summary
    transcript.insights = insights.model_dump()
    db.commit()
    db.refresh(transcript)

    return insights


@router.get(
    "/{attachment_id}/meeting",
    response_model=MeetingInsights,
    summary="Get structured meeting insights",
    description="Retrieve structured meeting insights, agenda, decisions, action items, and topic timelines.",
)
def get_meeting_insights(
    attachment_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> MeetingInsights:
    """Fetch meeting insights for an audio recording, generating on demand if not present."""
    from app.services.meeting_insights import get_meeting_insights_service
    from app.services.search_service import get_search_service

    attachment = (
        db.query(Attachment)
        .filter(Attachment.id == attachment_id, Attachment.user_id == current_user.id)
        .first()
    )
    if not attachment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Attachment not found",
        )

    transcript = db.query(Transcript).filter(Transcript.attachment_id == attachment_id).first()
    if not transcript:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Transcript not found for this attachment",
        )

    # Check if meeting insights already stored
    if transcript.insights and "per_topic_timeline" in transcript.insights:
        try:
            return MeetingInsights.model_validate(transcript.insights)
        except Exception:
            pass

    meeting_svc = get_meeting_insights_service()
    storage_root = get_storage_root()
    phys_path = storage_root / attachment.path if attachment.path else None

    insights = meeting_svc.generate_meeting_insights(
        transcript_text=transcript.text,
        segments=transcript.segments or [],
        total_duration=attachment.duration_sec or 0.0,
        audio_path=phys_path,
        output_language=transcript.language,
    )

    # Store in transcript.insights
    existing_insights = dict(transcript.insights or {})
    existing_insights.update(insights.model_dump())
    transcript.insights = existing_insights
    db.commit()
    db.refresh(transcript)

    # Index into Knowledge Vault
    conv_id = attachment.message.conversation_id if attachment.message else None
    get_search_service().index_transcript(current_user.id, conv_id, attachment.id, transcript)

    return insights


@router.post(
    "/{attachment_id}/meeting",
    response_model=MeetingInsights,
    summary="Force regenerate meeting insights",
    description="Forces re-extraction of meeting insights, agenda, decisions, and timeline charts.",
)
def force_regenerate_meeting_insights(
    attachment_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> MeetingInsights:
    """Force re-run meeting insights extraction and index action items into Knowledge Vault."""
    from app.services.meeting_insights import get_meeting_insights_service
    from app.services.search_service import get_search_service

    attachment = (
        db.query(Attachment)
        .filter(Attachment.id == attachment_id, Attachment.user_id == current_user.id)
        .first()
    )
    if not attachment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Attachment not found",
        )

    transcript = db.query(Transcript).filter(Transcript.attachment_id == attachment_id).first()
    if not transcript:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Transcript not found for this attachment",
        )

    meeting_svc = get_meeting_insights_service()
    storage_root = get_storage_root()
    phys_path = storage_root / attachment.path if attachment.path else None

    insights = meeting_svc.generate_meeting_insights(
        transcript_text=transcript.text,
        segments=transcript.segments or [],
        total_duration=attachment.duration_sec or 0.0,
        audio_path=phys_path,
        output_language=transcript.language,
    )

    existing_insights = dict(transcript.insights or {})
    existing_insights.update(insights.model_dump())
    transcript.insights = existing_insights
    db.commit()
    db.refresh(transcript)

    # Index into Knowledge Vault
    conv_id = attachment.message.conversation_id if attachment.message else None
    get_search_service().index_transcript(current_user.id, conv_id, attachment.id, transcript)

    return insights
