from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Header, HTTPException, status

from app.models.api import (
    AgentResponse,
    EnrollAgentRequest,
    EnrollAgentResponse,
    HeartbeatRequest,
    PullJobResponse,
    RegisterAgentRequest,
)
from app.models.domain import Agent
from app.services.repositories import store

router = APIRouter(prefix="/api/agents", tags=["agents"])


def _extract_bearer(authorization: str | None) -> str | None:
    if not authorization:
        return None
    prefix = "Bearer "
    if not authorization.startswith(prefix):
        return None
    return authorization[len(prefix):]


def _authenticate_agent(agent_id: str, authorization: str | None = Header(default=None)) -> str:
    token = _extract_bearer(authorization)
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized")

    authenticated_agent_id = store.get_agent_id_for_token(token)
    if authenticated_agent_id != agent_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized")

    store.touch_agent_token(token)
    return authenticated_agent_id


@router.post("/enroll", response_model=EnrollAgentResponse)
def enroll_agent(payload: EnrollAgentRequest) -> EnrollAgentResponse:
    if not store.consume_enrollment_code(payload.enrollment_code):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid enrollment code")

    agent = store.upsert_agent(Agent(agent_id=payload.agent_id, name=payload.name, capabilities=payload.capabilities))
    agent_token = store.issue_agent_token(agent.agent_id)

    return EnrollAgentResponse(
        agent_id=agent.agent_id,
        name=agent.name,
        status=agent.status,
        last_heartbeat=agent.last_heartbeat.isoformat(),
        agent_token=agent_token,
    )


@router.post("/register", response_model=AgentResponse)
def register_agent(payload: RegisterAgentRequest, authorization: str | None = Header(default=None)) -> AgentResponse:
    _authenticate_agent(payload.agent_id, authorization)
    agent = store.upsert_agent(Agent(agent_id=payload.agent_id, name=payload.name, capabilities=payload.capabilities))
    return AgentResponse(
        agent_id=agent.agent_id,
        name=agent.name,
        status=agent.status,
        last_heartbeat=agent.last_heartbeat.isoformat(),
    )


@router.post("/{agent_id}/heartbeat", response_model=AgentResponse)
def heartbeat(agent_id: str, payload: HeartbeatRequest, _: str = Depends(_authenticate_agent)) -> AgentResponse:
    agent = store.get_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found")

    agent.status = payload.status
    agent.last_heartbeat = datetime.now(UTC)
    store.upsert_agent(agent)

    return AgentResponse(
        agent_id=agent.agent_id,
        name=agent.name,
        status=agent.status,
        last_heartbeat=agent.last_heartbeat.isoformat(),
    )


@router.get("/{agent_id}/next-job", response_model=PullJobResponse | None)
def next_job(agent_id: str, _: str = Depends(_authenticate_agent)) -> PullJobResponse | None:
    job = store.next_queued_job_for_agent(agent_id)
    if not job:
        return None

    return PullJobResponse(job_id=job.job_id, target_ref=job.target_ref, source_type=job.source_type)

