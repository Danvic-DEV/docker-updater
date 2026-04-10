from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, Field


AgentStatus = Literal["online", "offline"]
JobStatus = Literal["queued", "in_progress", "completed", "failed", "rolled_back"]


class Agent(BaseModel):
    agent_id: str
    name: str
    status: AgentStatus = "online"
    last_heartbeat: datetime = Field(default_factory=lambda: datetime.now(UTC))
    capabilities: dict[str, str] = Field(default_factory=dict)


class UpdateJob(BaseModel):
    job_id: str
    target_ref: str
    source_type: Literal["registry", "git"]
    target_agent_id: str
    status: JobStatus = "queued"
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    logs: list[str] = Field(default_factory=list)
