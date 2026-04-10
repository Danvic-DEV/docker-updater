import uuid

from fastapi import APIRouter, HTTPException

from app.models.api import CreateJobRequest, JobResponse
from app.models.domain import UpdateJob
from app.services.repositories import store

router = APIRouter(prefix="/api/jobs", tags=["admin-jobs"])


def _to_response(job: UpdateJob) -> JobResponse:
    return JobResponse(
        job_id=job.job_id,
        target_ref=job.target_ref,
        source_type=job.source_type,
        target_agent_id=job.target_agent_id,
        status=job.status,
        created_at=job.created_at.isoformat(),
        updated_at=job.updated_at.isoformat(),
        logs=job.logs,
    )


@router.post("", response_model=JobResponse)
def create_job(payload: CreateJobRequest) -> JobResponse:
    if payload.source_type not in {"registry", "git"}:
        raise HTTPException(status_code=400, detail="source_type must be registry or git")

    if not store.get_agent(payload.target_agent_id):
        raise HTTPException(status_code=404, detail="Target agent not found")

    job = store.create_job(
        UpdateJob(
            job_id=str(uuid.uuid4()),
            target_ref=payload.target_ref,
            source_type=payload.source_type,
            target_agent_id=payload.target_agent_id,
        )
    )
    return _to_response(job)


@router.get("", response_model=list[JobResponse])
def list_jobs() -> list[JobResponse]:
    return [_to_response(job) for job in store.list_jobs()]


@router.get("/{job_id}", response_model=JobResponse)
def get_job(job_id: str) -> JobResponse:
    job = store.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return _to_response(job)
