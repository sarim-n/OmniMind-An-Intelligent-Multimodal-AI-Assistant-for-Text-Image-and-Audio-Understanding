"""Unit and integration tests for background job runner and lifecycle."""

import pytest
from httpx import AsyncClient
from sqlalchemy.orm import Session

from app.main import mark_orphan_jobs_failed
from app.models.job import Job
from app.models.user import User
from app.services.job_service import get_job_service


def test_job_service_lifecycle(db: Session, test_user: User) -> None:
    job_service = get_job_service()

    # 1. Create job
    job = job_service.create_job(user_id=test_user.id, job_type="test_job", db=db)
    assert job.id is not None
    assert job.status == "queued"
    assert job.progress == 0.0

    # 2. Update status and progress
    job_service.update_job_status(job_id=job.id, status="running", progress=0.5)
    db.refresh(job)
    assert job.status == "running"
    assert job.progress == 0.5

    # 3. Mark completed
    job_service.update_job_status(
        job_id=job.id,
        status="done",
        progress=1.0,
        result={"summary": "all done"},
    )
    db.refresh(job)
    assert job.status == "done"
    assert job.progress == 1.0
    assert job.result == {"summary": "all done"}


def test_mark_orphan_jobs_failed_on_startup(db: Session, test_user: User) -> None:
    # Create an interrupted job left in 'running' state
    orphan = Job(
        user_id=test_user.id,
        type="audio_transcription",
        status="running",
        progress=0.3,
    )
    db.add(orphan)
    db.commit()
    db.refresh(orphan)

    # Run startup cleanup
    count = mark_orphan_jobs_failed()
    assert count >= 1

    db.refresh(orphan)
    assert orphan.status == "failed"
    assert "interrupted" in (orphan.error or "").lower()


@pytest.mark.asyncio
async def test_job_endpoint_cross_user_isolation(
    client: AsyncClient,
    auth_headers: dict[str, str],
    auth_headers_b: dict[str, str],
    db: Session,
    test_user: User,
) -> None:
    # Create job owned by User A
    job_service = get_job_service()
    job = job_service.create_job(user_id=test_user.id, job_type="sample", db=db)

    # User A accesses job -> 200 OK
    res_a = await client.get(f"/api/v1/jobs/{job.id}", headers=auth_headers)
    assert res_a.status_code == 200
    assert res_a.json()["id"] == job.id

    # User B accesses User A's job -> 404 NOT FOUND
    res_b = await client.get(f"/api/v1/jobs/{job.id}", headers=auth_headers_b)
    assert res_b.status_code == 404
