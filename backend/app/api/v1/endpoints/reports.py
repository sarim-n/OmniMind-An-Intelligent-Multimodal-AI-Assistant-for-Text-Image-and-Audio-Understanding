"""Report management and PDF download endpoints."""

from __future__ import annotations

import re
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.logging import get_logger
from app.core.security import get_current_user
from app.db.session import get_db
from app.models.conversation import Conversation
from app.models.report import Report
from app.models.user import User
from app.schemas.report import (
    ReportCreateRequest,
    ReportCreateResponse,
    ReportListItem,
    ReportResponse,
    ReportSchema,
)
from app.services.job_service import get_job_service
from app.services.pdf_service import get_pdf_service
from app.services.report_service import get_report_service

logger = get_logger(__name__)
router = APIRouter()


def _sanitize_filename(name: str) -> str:
    """Sanitize string for safe Content-Disposition filename header."""
    clean = re.sub(r'[\\/*?:"<>|]', "_", name).strip()
    return clean or "report"


@router.post(
    "",
    response_model=ReportCreateResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Generate multimodal intelligence report",
    description="Enqueue an asynchronous background job to synthesize stored conversation data into a report.",
)
async def create_report(
    payload: ReportCreateRequest,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ReportCreateResponse:
    """Initiate report generation job with strict user verification."""
    conv = (
        db.query(Conversation)
        .filter(
            Conversation.id == payload.conversation_id,
            Conversation.user_id == current_user.id,
        )
        .first()
    )
    if not conv:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found or access denied",
        )

    job_svc = get_job_service()
    job = job_svc.create_job(
        user_id=current_user.id,
        job_type="report_generation",
        db=db,
    )

    report_svc = get_report_service()
    background_tasks.add_task(
        report_svc.generate_report_job,
        job.id,
        payload.conversation_id,
        current_user.id,
        payload.options.model_dump(),
    )

    return ReportCreateResponse(job_id=job.id, status="pending")


@router.get(
    "",
    response_model=list[ReportListItem],
    summary="List user reports",
    description="Retrieve all generated reports associated with conversations owned by the authenticated user.",
)
async def list_reports(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[ReportListItem]:
    """List reports strictly scoped to current user."""
    reports = (
        db.query(Report)
        .join(Conversation, Report.conversation_id == Conversation.id)
        .filter(Conversation.user_id == current_user.id)
        .order_by(Report.created_at.desc())
        .all()
    )

    return [
        ReportListItem(
            id=r.id,
            conversation_id=r.conversation_id,
            title=r.title,
            created_at=r.created_at,
            pdf_path=r.pdf_path,
        )
        for r in reports
    ]


@router.get(
    "/{report_id}",
    response_model=ReportResponse,
    summary="Get report details",
    description="Retrieve full structured JSON content for a specific report.",
)
async def get_report(
    report_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ReportResponse:
    """Retrieve individual report ensuring strict ownership isolation."""
    report = (
        db.query(Report)
        .join(Conversation, Report.conversation_id == Conversation.id)
        .filter(Report.id == report_id, Conversation.user_id == current_user.id)
        .first()
    )
    if not report:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Report not found or access denied",
        )

    content_schema = (
        report.content
        if isinstance(report.content, ReportSchema)
        else ReportSchema(**report.content)
    )

    return ReportResponse(
        id=report.id,
        conversation_id=report.conversation_id,
        title=report.title,
        created_at=report.created_at,
        pdf_path=report.pdf_path,
        content=content_schema,
    )


@router.get(
    "/{report_id}/pdf",
    summary="Download compiled PDF report",
    description="Download the compiled PDF report, generating it on demand if the file is missing from disk.",
)
async def download_report_pdf(
    report_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> FileResponse:
    """Download PDF file with on-demand build fallback and strict authorization."""
    report = (
        db.query(Report)
        .join(Conversation, Report.conversation_id == Conversation.id)
        .filter(Report.id == report_id, Conversation.user_id == current_user.id)
        .first()
    )
    if not report:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Report not found or access denied",
        )

    pdf_file_path = Path(report.pdf_path) if report.pdf_path else None
    if not pdf_file_path or not pdf_file_path.exists():
        # Build PDF on demand from stored JSON content
        pdf_file_path = settings.REPORTS_DIR / f"{report.id}.pdf"
        try:
            content_schema = (
                report.content
                if isinstance(report.content, ReportSchema)
                else ReportSchema(**report.content)
            )
            pdf_svc = get_pdf_service()
            pdf_svc.build_pdf(content_schema, pdf_file_path)
            report.pdf_path = str(pdf_file_path)
            db.commit()
            db.refresh(report)
        except Exception as e:
            logger.error("Failed on-demand PDF build", report_id=report.id, error=str(e))
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to compile PDF document: {e}",
            )

    safe_name = _sanitize_filename(report.title)
    return FileResponse(
        path=str(pdf_file_path),
        media_type="application/pdf",
        filename=f"{safe_name}.pdf",
        headers={"Content-Disposition": f'attachment; filename="{safe_name}.pdf"'},
    )


@router.delete(
    "/{report_id}",
    status_code=status.HTTP_200_OK,
    summary="Delete report",
    description="Purge a report record from the database and remove its compiled PDF file from disk.",
)
async def delete_report(
    report_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, str]:
    """Delete report record and associated PDF artifact."""
    report = (
        db.query(Report)
        .join(Conversation, Report.conversation_id == Conversation.id)
        .filter(Report.id == report_id, Conversation.user_id == current_user.id)
        .first()
    )
    if not report:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Report not found or access denied",
        )

    # Delete PDF file if present on disk
    if report.pdf_path:
        p = Path(report.pdf_path)
        try:
            if p.exists() and p.is_file():
                p.unlink(missing_ok=True)
                logger.info("Purged report PDF file from disk", path=str(p))
        except Exception as e:
            logger.warning("Failed to delete PDF file on disk", path=str(p), error=str(e))

    db.delete(report)
    db.commit()
    logger.info("Deleted report from database", report_id=report_id, user_id=current_user.id)
    return {"status": "deleted", "id": report_id}
