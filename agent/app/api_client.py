from typing import Any

import httpx

from app.config import settings


class PrimaryApiClient:
    def __init__(self) -> None:
        self._client = httpx.Client(base_url=settings.primary_api_base_url, timeout=10.0)
        self._agent_token: str | None = settings.agent_token or settings.agent_shared_token

    @property
    def _headers(self) -> dict[str, str]:
        if not self._agent_token:
            return {}
        return {"Authorization": f"Bearer {self._agent_token}"}

    def enroll(self) -> dict[str, Any]:
        if not settings.enrollment_code:
            raise RuntimeError("ENROLLMENT_CODE is required when AGENT_TOKEN is not set")

        response = self._client.post(
            "/api/agents/enroll",
            json={
                "enrollment_code": settings.enrollment_code,
                "agent_id": settings.agent_id,
                "name": settings.agent_name,
                "capabilities": {"docker": "true", "source_types": "registry,git"},
            },
        )
        response.raise_for_status()
        payload = response.json()
        self._agent_token = payload["agent_token"]
        return payload

    def register(self) -> dict[str, Any]:
        response = self._client.post(
            "/api/agents/register",
            json={
                "agent_id": settings.agent_id,
                "name": settings.agent_name,
                "capabilities": {"docker": "true", "source_types": "registry,git"},
            },
            headers=self._headers,
        )
        response.raise_for_status()
        return response.json()

    def heartbeat(self) -> dict[str, Any]:
        response = self._client.post(
            f"/api/agents/{settings.agent_id}/heartbeat",
            json={"status": "online"},
            headers=self._headers,
        )
        response.raise_for_status()
        return response.json()

    def pull_next_job(self) -> dict[str, Any] | None:
        response = self._client.get(f"/api/agents/{settings.agent_id}/next-job", headers=self._headers)
        response.raise_for_status()
        return response.json()

    def report_progress(self, job_id: str, status: str, log_line: str | None = None) -> None:
        self._client.post(
            f"/api/jobs/{job_id}/progress",
            json={"status": status, "log_line": log_line},
            headers=self._headers,
        ).raise_for_status()
