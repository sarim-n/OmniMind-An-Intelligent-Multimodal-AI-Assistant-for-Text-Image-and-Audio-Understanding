"""Job status query endpoints."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.security import get_current_user
from app.db.session import get_db
from app.models.job import Job
from app.models.user import User
from app.schemas.job import JobRead
from app.services.job_service import get_job_service

router = APIRouter()


@router.get(
    "/{job_id}",
    response_model=JobRead,
    summary="Get background job status",
    description="Retrieve execution state, progress, and result for an asynchronous job.",
)
def get_job_status(
    job_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Job:
    """Retrieve job scoped strictly to the authenticated user."""
    job = get_job_service().get_job(job_id=job_id, user_id=current_user.id, db=db)
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job not found",
        )
    return job
