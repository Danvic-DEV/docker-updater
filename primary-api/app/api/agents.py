from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Header, HTTPException, status

from app.core.config import settings
from app.models.api import AgentResponse, HeartbeatRequest, PullJobResponse, RegisterAgentRequest
from app.models.domain import Agent
from app.services.repositories import store

router = APIRouter(prefix="/api/agents", tags=["agents"])


def _check_token(authorization: str | None = Header(default=None)) -> None:
    if authorization != f"Bearer {settings.agent_shared_token}":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized")


@router.post("/register", response_model=AgentResponse, dependencies=[Depends(_check_token)])
def register_agent(payload: RegisterAgentRequest) -> AgentResponse:
    agent = store.upsert_agent(Agent(agent_id=payload.agent_id, name=payload.name, capabilities=payload.capabilities))
    return AgentResponse(
        agent_id=agent.agent_id,
        name=agent.name,
        status=agent.status,
        last_heartbeat=agent.last_heartbeat.isoformat(),
    )


@router.post("/{agent_id}/heartbeat", response_model=AgentResponse, dependencies=[Depends(_check_token)])
def heartbeat(agent_id: str, payload: HeartbeatRequest) -> AgentResponse:
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


@router.get("/{agent_id}/next-job", response_model=PullJobResponse | None, dependencies=[Depends(_check_token)])
def next_job(agent_id: str) -> PullJobResponse | None:
    job = store.next_queued_job_for_agent(agent_id)
    if not job:
        return None

    return PullJobResponse(job_id=job.job_id, target_ref=job.target_ref, source_type=job.source_type)


@router.get("", response_model=list[AgentResponse])
def list_agents() -> list[AgentResponse]:
    return [
        AgentResponse(
            agent_id=agent.agent_id,
            name=agent.name,
            status=agent.status,
            last_heartbeat=agent.last_heartbeat.isoformat(),
        )
        for agent in store.list_agents()
    ]
