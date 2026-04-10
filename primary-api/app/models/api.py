from pydantic import BaseModel, Field

from app.models.domain import AgentStatus, JobStatus


class HealthResponse(BaseModel):
    status: str = "ok"


class RegisterAgentRequest(BaseModel):
    agent_id: str
    name: str
    capabilities: dict[str, str] = Field(default_factory=dict)


class HeartbeatRequest(BaseModel):
    status: AgentStatus = "online"


class AgentResponse(BaseModel):
    agent_id: str
    name: str
    status: AgentStatus
    last_heartbeat: str


class CreateJobRequest(BaseModel):
    target_ref: str = Field(description="Image tag or Git ref")
    source_type: str = Field(description="registry|git")
    target_agent_id: str


class JobResponse(BaseModel):
    job_id: str
    target_ref: str
    source_type: str
    target_agent_id: str
    status: JobStatus
    created_at: str
    updated_at: str
    logs: list[str]


class PullJobResponse(BaseModel):
    job_id: str
    target_ref: str
    source_type: str


class JobProgressRequest(BaseModel):
    status: JobStatus
    log_line: str | None = None
