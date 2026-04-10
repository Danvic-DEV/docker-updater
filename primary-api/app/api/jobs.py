import uuid

from fastapi import APIRouter, Depends, Header, HTTPException, status

from app.core.config import settings
from app.models.api import CreateJobRequest, JobProgressRequest, JobResponse
from app.models.domain import UpdateJob
from app.services.repositories import store

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


def _extract_bearer(authorization: str | None) -> str | None:
    if not authorization:
        return None
    prefix = "Bearer "
    if not authorization.startswith(prefix):
        return None
    return authorization[len(prefix):]


def _authenticate_agent_token(authorization: str | None = Header(default=None)) -> str | None:
    token = _extract_bearer(authorization)
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized")

    # Backward compatibility for existing shared-token setups.
    if settings.agent_shared_token and token == settings.agent_shared_token:
        return None

    agent_id = store.get_agent_id_for_token(token)
    if not agent_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized")

    store.touch_agent_token(token)
    return agent_id


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


@router.post("/{job_id}/progress", response_model=JobResponse)
def update_progress(job_id: str, payload: JobProgressRequest, authenticated_agent_id: str | None = Depends(_authenticate_agent_token)) -> JobResponse:
    existing = store.get_job(job_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Job not found")

    if authenticated_agent_id is not None and existing.target_agent_id != authenticated_agent_id:
        raise HTTPException(status_code=403, detail="Agent cannot update this job")

    job = store.update_job_status(job_id, status=payload.status, log_line=payload.log_line)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return _to_response(job)
