"""In-process background job execution and state management service."""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Coroutine
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.models.job import Job

logger = get_logger(__name__)


class JobService:
    """Manages asynchronous job registration, lifecycle status, and execution."""

    _instance: JobService | None = None

    @classmethod
    def get_instance(cls) -> JobService:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def create_job(self, user_id: str, job_type: str, db: Session) -> Job:
        """Register a new job in queued state."""
        job = Job(
            id=str(uuid.uuid4()),
            user_id=user_id,
            type=job_type,
            status="queued",
            progress=0.0,
        )
        db.add(job)
        db.commit()
        db.refresh(job)
        logger.info("Created background job", job_id=job.id, job_type=job_type, user_id=user_id)
        return job

    def update_job_status(
        self,
        job_id: str,
        status: str,
        progress: float | None = None,
        result: dict[str, Any] | None = None,
        error: str | None = None,
    ) -> None:
        """Update job status and progress using an isolated database session."""
        import app.db.session

        try:
            with app.db.session.SessionLocal() as session:
                job = session.get(Job, job_id)
                if not job:
                    logger.warning("Job not found during status update", job_id=job_id)
                    return

                job.status = status
                if progress is not None:
                    job.progress = max(0.0, min(1.0, round(progress, 2)))
                if result is not None:
                    job.result = result
                if error is not None:
                    job.error = error
                job.updated_at = datetime.now(UTC)

                session.commit()
                logger.info(
                    "Updated job status",
                    job_id=job_id,
                    status=status,
                    progress=job.progress,
                )
        except Exception as e:
            logger.error("Failed to update job status", job_id=job_id, error=str(e))

    def get_job(self, job_id: str, user_id: str, db: Session) -> Job | None:
        """Retrieve job ensuring strict ownership isolation."""
        return db.query(Job).filter(Job.id == job_id, Job.user_id == user_id).first()

    def spawn_coroutine(self, coro: Coroutine[Any, Any, None]) -> asyncio.Task[None]:
        """Fire-and-forget in-process execution via asyncio background task."""
        loop = asyncio.get_running_loop()
        return loop.create_task(coro)


def get_job_service() -> JobService:
    """Retrieve singleton JobService instance."""
    return JobService.get_instance()
