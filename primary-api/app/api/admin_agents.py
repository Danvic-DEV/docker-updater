from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException

from app.models.api import AgentResponse
from app.models.domain import Agent
from app.services.repositories import store

router = APIRouter(prefix="/api/agents", tags=["admin-agents"])


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
