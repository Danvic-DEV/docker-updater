import uuid

from fastapi import APIRouter, HTTPException

from app.models.api import JobProgressRequest, JobResponse
from app.models.domain import UpdateJob
from app.services.repositories import store

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


def _to_response(job: UpdateJob) -> JobResponse:
    return JobResponse(
        job_id=job.job_id,
        target_ref=job.target_ref,
        target_container_name=job.target_container_name,
        source_type=job.source_type,
        target_agent_id=job.target_agent_id,
        status=job.status,
        created_at=job.created_at.isoformat(),
        updated_at=job.updated_at.isoformat(),
        logs=job.logs,
    )


@router.post("/{job_id}/progress", response_model=JobResponse)
def update_progress(job_id: str, payload: JobProgressRequest) -> JobResponse:
    existing = store.get_job(job_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Job not found")

    job = store.update_job_status(job_id, status=payload.status, log_line=payload.log_line)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return _to_response(job)
