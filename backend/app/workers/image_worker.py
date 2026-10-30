"""Background worker executing asynchronous image analysis jobs."""

from __future__ import annotations

from pathlib import Path

from app.core.logging import get_logger
from app.services.image_pipeline import run_image_pipeline
from app.services.job_service import get_job_service

logger = get_logger(__name__)


async def execute_image_analysis_job(
    job_id: str,
    attachment_id: str,
    file_path: Path | str,
    user_id: str,
    enhance: bool = False,
) -> None:
    """Asynchronous background worker executing image understanding pipeline."""
    job_service = get_job_service()

    logger.info(
        "Starting background image analysis job",
        job_id=job_id,
        attachment_id=attachment_id,
        user_id=user_id,
    )
    job_service.update_job_status(job_id=job_id, status="running", progress=0.1)

    try:
        # Run pipeline
        analysis_result = await run_image_pipeline(
            attachment_id=attachment_id,
            file_path=file_path,
            user_id=user_id,
            enhance=enhance,
        )

        job_service.update_job_status(job_id=job_id, status="running", progress=0.8)

        # Complete job with analysis payload
        result_payload = analysis_result.model_dump()
        job_service.update_job_status(
            job_id=job_id,
            status="done",
            progress=1.0,
            result=result_payload,
        )

        # Index image caption, OCR, and SigLIP visual embedding into Knowledge Vault
        try:
            from app.services.search_service import get_search_service

            get_search_service().index_image_analysis(
                user_id=user_id,
                conversation_id=None,
                attachment_id=attachment_id,
                analysis_data=analysis_result,
                image_path=file_path,
            )
        except Exception as idx_err:
            logger.warning("Knowledge Vault indexing failed in image worker", error=str(idx_err))

        logger.info(
            "Successfully completed image analysis job",
            job_id=job_id,
            attachment_id=attachment_id,
        )

    except Exception as e:
        logger.error(
            "Image analysis background job failed",
            job_id=job_id,
            attachment_id=attachment_id,
            error=str(e),
        )
        job_service.update_job_status(
            job_id=job_id,
            status="failed",
            progress=1.0,
            error=str(e),
        )
