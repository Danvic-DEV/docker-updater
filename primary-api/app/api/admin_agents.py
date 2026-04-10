from datetime import UTC, datetime
import shlex

from fastapi import APIRouter, HTTPException, Request

from app.core.config import settings
from app.models.api import (
    AgentResponse,
    AgentBootstrapCommandRequest,
    AgentBootstrapCommandResponse,
    CreateEnrollmentCodeRequest,
    EnrollmentCodeResponse,
)
from app.models.domain import Agent
from app.services.repositories import store

router = APIRouter(prefix="/api/agents", tags=["admin-agents"])


@router.post("/enrollment-codes", response_model=EnrollmentCodeResponse)
def create_enrollment_code(payload: CreateEnrollmentCodeRequest) -> EnrollmentCodeResponse:
    enrollment_code, expires_at = store.create_enrollment_code(payload.ttl_minutes)
    return EnrollmentCodeResponse(enrollment_code=enrollment_code, expires_at=expires_at.isoformat())


@router.post("/bootstrap-command", response_model=AgentBootstrapCommandResponse)
def create_bootstrap_command(
    payload: AgentBootstrapCommandRequest,
    request: Request,
) -> AgentBootstrapCommandResponse:
    enrollment_code, expires_at = store.create_enrollment_code(60)

    default_base_url = str(request.base_url).rstrip("/")
    primary_base_url = payload.primary_api_base_url.strip() if payload.primary_api_base_url else default_base_url.replace(":8001", ":8000")

    command = (
        "docker run -d --name "
        + shlex.quote(f"docker-updater-agent-{payload.agent_id}")
        + " --restart unless-stopped"
        + " -e PRIMARY_API_BASE_URL="
        + shlex.quote(primary_base_url)
        + " -e AGENT_ID="
        + shlex.quote(payload.agent_id)
        + " -e AGENT_NAME="
        + shlex.quote(payload.agent_name)
        + " -e ENROLLMENT_CODE="
        + shlex.quote(enrollment_code)
        + " -v /var/run/docker.sock:/var/run/docker.sock "
        + shlex.quote(payload.agent_image.strip() if payload.agent_image else settings.agent_image)
    )

    return AgentBootstrapCommandResponse(
        enrollment_code=enrollment_code,
        expires_at=expires_at.isoformat(),
        command=command,
    )


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


@router.get("/{agent_id}", response_model=AgentResponse)
def get_agent(agent_id: str) -> AgentResponse:
    agent = store.get_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    return AgentResponse(
        agent_id=agent.agent_id,
        name=agent.name,
        status=agent.status,
        last_heartbeat=agent.last_heartbeat.isoformat(),
    )
