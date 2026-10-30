"""Background worker tasks for audio processing and transcription."""

from __future__ import annotations

import asyncio
from pathlib import Path

from app.core.logging import get_logger
from app.models.transcript import Transcript
from app.services.audio_service import get_audio_service
from app.services.job_service import get_job_service

logger = get_logger(__name__)


async def execute_transcription_job(
    job_id: str,
    attachment_id: str,
    file_path: Path,
    language: str | None = None,
    translate: bool = False,
    word_timestamps: bool = False,
) -> None:
    """Asynchronous background worker executing audio transcription and storing results."""
    job_service = get_job_service()
    audio_service = get_audio_service()

    logger.info(
        "Starting background transcription job",
        job_id=job_id,
        attachment_id=attachment_id,
    )
    job_service.update_job_status(job_id=job_id, status="running", progress=0.1)

    try:
        # Run model inference in threadpool to keep event loop free
        task_mode = "translate" if translate else "transcribe"
        result, timing_ms = await asyncio.to_thread(
            audio_service.transcribe,
            file_path=file_path,
            language=language,
            task=task_mode,
            word_timestamps=word_timestamps,
        )

        job_service.update_job_status(job_id=job_id, status="running", progress=0.7)

        # Persist transcript in database
        import app.db.session

        transcript_id = ""
        with app.db.session.SessionLocal() as session:
            # Check if transcript already exists for this attachment
            existing = (
                session.query(Transcript).filter(Transcript.attachment_id == attachment_id).first()
            )
            if existing:
                existing.language = result.language
                existing.text = result.text
                existing.segments = [s.model_dump() for s in result.segments]
                transcript_id = existing.id
            else:
                transcript = Transcript(
                    attachment_id=attachment_id,
                    language=result.language,
                    text=result.text,
                    segments=[s.model_dump() for s in result.segments],
                )
                session.add(transcript)
                session.flush()
                transcript_id = transcript.id

            # Auto-run meeting insights if audio duration >= MEETING_MIN_DURATION_SEC
            from app.core.config import settings
            from app.models.attachment import Attachment
            from app.services.meeting_insights import get_meeting_insights_service
            from app.services.search_service import get_search_service

            att = session.query(Attachment).filter(Attachment.id == attachment_id).first()
            if result.duration >= settings.MEETING_MIN_DURATION_SEC:
                try:
                    meeting_svc = get_meeting_insights_service()
                    mi = meeting_svc.generate_meeting_insights(
                        transcript_text=result.text,
                        segments=[s.model_dump() for s in result.segments],
                        total_duration=result.duration,
                        audio_path=file_path,
                        output_language=result.language,
                    )
                    curr_insights = dict(existing.insights or {}) if existing else {}
                    curr_insights.update(mi.model_dump())
                    target_transcript = existing or transcript
                    target_transcript.insights = curr_insights
                    session.commit()
                except Exception as mi_err:
                    logger.warning(
                        "Auto meeting insights generation failed in worker",
                        error=str(mi_err),
                    )

            session.commit()

            # Index transcript and action items into Knowledge Vault
            if att:
                try:
                    conv_id = att.message.conversation_id if att.message else None
                    target_transcript = existing or transcript
                    get_search_service().index_transcript(
                        user_id=att.user_id,
                        conversation_id=conv_id,
                        attachment_id=attachment_id,
                        transcript_data=target_transcript,
                    )
                except Exception as idx_err:
                    logger.warning(
                        "Knowledge Vault indexing failed in audio worker",
                        error=str(idx_err),
                    )

        # Finalize job
        result_payload = {
            "transcript_id": transcript_id,
            "attachment_id": attachment_id,
            "language": result.language,
            "language_probability": result.language_probability,
            "duration": result.duration,
            "text": result.text,
            "segment_count": len(result.segments),
            "timing_ms": timing_ms,
        }
        job_service.update_job_status(
            job_id=job_id, status="done", progress=1.0, result=result_payload
        )
        logger.info(
            "Completed transcription job successfully",
            job_id=job_id,
            transcript_id=transcript_id,
        )

    except Exception as e:
        logger.error("Transcription job failed", job_id=job_id, error=str(e))
        job_service.update_job_status(job_id=job_id, status="failed", progress=1.0, error=str(e))
