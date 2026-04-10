# Docker Updater

Monorepo for a Docker update orchestration system with:
- Primary control plane API: FastAPI + PostgreSQL
- Primary web UI: React + Vite
- Remote agent: Python polling worker

## Install Primary with docker run

Pull and start the Primary container directly:

```bash
docker run -d \
	--name docker-updater-primary \
	--restart unless-stopped \
	-p 5432:5432 \
	-p 8000:8000 \
	-p 5173:5173 \
	-e ADMIN_API_TOKEN=change-me \
	-e AGENT_IMAGE=ghcr.io/danvic-dev/docker-updater-agent:latest \
	-e PRIMARY_EMBEDDED_AGENT_ENABLE=false \
	-v primary_data:/config \
	-v /var/run/docker.sock:/var/run/docker.sock \
	ghcr.io/danvic-dev/docker-updater-primary:latest
```

Then open:
- API docs: http://localhost:8000/docs
- Web UI: http://localhost:5173

## Quick Start (Fresh Install)

1. Reset old local state (optional but recommended for clean-break auth):

```bash
docker compose down -v
```

2. Start local stack:

```bash
docker compose up --build
```

3. Open:
- API docs: http://localhost:8000/docs
- Web UI: http://localhost:5173

## Current Status

Implemented MVP with:
- PostgreSQL-backed agents and job queue
- Agent enrollment flow with per-agent credentials
- Agent polling, job execution, and progress reporting
- Container image pull + container replacement execution
- Dashboard for agents, targets, and job logs

## Stateless Agent Enrollment (No Persistent Agent Storage)

The agent can run without persistent local storage. It only needs env vars and `/var/run/docker.sock` mounted.

### 1) Create an enrollment code from Primary

Use the admin token configured on Primary (`ADMIN_API_TOKEN`, default: `dev-admin-token`):

```bash
curl -X POST http://localhost:8000/api/agents/enrollment-codes \
	-H 'Authorization: Bearer dev-admin-token' \
	-H 'Content-Type: application/json' \
	-d '{"ttl_minutes":60}'
```

### 2) Start agent with env vars only

```bash
docker run -d \
	--name docker-updater-agent \
	-e PRIMARY_API_BASE_URL=http://<primary-host>:8000 \
	-e AGENT_ID=<agent-id> \
	-e AGENT_NAME=<agent-name> \
	-e ENROLLMENT_CODE=<code-from-step-1> \
	-v /var/run/docker.sock:/var/run/docker.sock \
	ghcr.io/danvic-dev/docker-updater-agent:latest
```

The agent auto-enrolls on startup, receives a per-agent token, and uses it for API auth during that run.

### Auth notes

- Agent auth is per-agent token only (issued during enrollment).
- Enrollment codes are one-time use and time-limited.
- Admin operations (creating enrollment codes / bootstrap commands) require `ADMIN_API_TOKEN`.

## GHCR Auto Build

GitHub Actions publish separate images to GHCR with path-based triggers:
- Primary image: `ghcr.io/danvic-dev/docker-updater-primary`
	- Triggered by changes under `primary/`, `primary-api/`, `primary-web/`, and `agent/`.
- Agent image: `ghcr.io/danvic-dev/docker-updater-agent`
	- Triggered by changes under `agent/`.

Workflows:
- `.github/workflows/build-primary.yml`
- `.github/workflows/build-agent.yml`
