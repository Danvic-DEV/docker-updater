# Docker Updater

Monorepo for a Docker update orchestration system with:
- Primary control plane API: FastAPI + PostgreSQL
- Primary web UI: React + Vite
- Remote agent: Python polling worker

## Install Primary with docker run

Pull and start the Primary container directly:

```bash
docker run -d \
	--name docker-updater \
	--restart unless-stopped \
	-p 58000:58000 \
	-p 5173:5173 \
	-v primary_data:/config \
	-v /var/run/docker.sock:/var/run/docker.sock \
	ghcr.io/danvic-dev/docker-updater-primary:latest
```

Optional env vars:

```bash
# Override the agent image used in generated bootstrap commands
-e AGENT_IMAGE=ghcr.io/danvic-dev/docker-updater-agent:latest

# Enable/disable the embedded agent inside primary
-e PRIMARY_EMBEDDED_AGENT_ENABLE=true
```

Then open:
- Web UI: http://localhost:5173

(Port 58000 is exposed for agents only. Port 8001 for admin API is not exposed.)

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
- Web UI: http://localhost:5173

**Port layout:**
- 58000: Agent API (exposed for agent heartbeat + job updates)
- 8001: Admin API (internal only, not exposed - used by UI)
- 5173: Web UI (exposed)

## Current Status

Implemented MVP with:
- PostgreSQL-backed agents and job queue
- Agent enrollment flow with per-agent credentials
- Agent polling, job execution, and progress reporting
- Container image pull + container replacement execution
- Dashboard for agents, targets, and job logs

## Stateless Agent Enrollment (No Persistent Agent Storage)

The agent can run without persistent local storage. It only needs env vars and `/var/run/docker.sock` mounted.

### 1) Create an enrollment code from UI

In the web UI (http://localhost:5173), go to Settings and create an enrollment code. Or use the admin API (internal only):

```bash
curl -X POST http://localhost:8001/api/agents/enrollment-codes \
	-H 'Content-Type: application/json' \
	-d '{"ttl_minutes":60}'
```

Note: This endpoint is only available on port 8001, which is not exposed outside the container. The web UI is the primary interface for creating enrollment codes.

### 2) Start agent with env vars only

```bash
docker run -d \
	--name docker-updater-agent \
	-e PRIMARY_API_BASE_URL=http://<primary-host>:58000 \
	-e AGENT_ID=<agent-id> \
	-e AGENT_NAME=<agent-name> \
	-e ENROLLMENT_CODE=<code-from-step-1> \
	-v /var/run/docker.sock:/var/run/docker.sock \
	ghcr.io/danvic-dev/docker-updater-agent:latest
```

The agent auto-enrolls on startup, receives a per-agent token, and uses it for API auth during that run.

### Architecture

The system uses a **dual-port security boundary** model:

- **Port 58000 (Agent API)**: Exposed externally
  - Agent heartbeat, job polling, and progress updates
  - Authentication: Per-agent bearer tokens (issued after enrollment)
  - Used by: Remote agents only

- **Port 8001 (Admin API)**: Internal only, not exposed
  - Enrollment code generation and bootstrap command generation
  - Job creation and management
  - Container inventory queries
  - Authentication: None (internal only)
  - Used by: Web UI only

- **Port 5173 (Web UI)**: Exposed externally
  - React app served by Vite
  - In dev: Proxies admin API calls through `/admin-api` to internal port 8001
  - In prod: Direct calls to `localhost:8001` (same container)

**Security Model:**
- External callers can only reach ports 58000 (agents) and 5173 (UI)
- Port 8001 is bound to localhost and inaccessible from outside the container
- UI operations cannot be called directly from outside; only agents with valid per-agent tokens can access the API
- Each agent gets a unique bearer token after enrollment; tokens are never shared

## GHCR Auto Build

GitHub Actions publish separate images to GHCR with path-based triggers:
- Primary image: `ghcr.io/danvic-dev/docker-updater-primary`
	- Triggered by changes under `primary/`, `primary-api/`, `primary-web/`, and `agent/`.
- Agent image: `ghcr.io/danvic-dev/docker-updater-agent`
	- Triggered by changes under `agent/`.

Workflows:
- `.github/workflows/build-primary.yml`
- `.github/workflows/build-agent.yml`

## Deployment Notes

**Development (docker compose up):**
- Browser on host machine cannot directly reach internal port 8001
- Solution: Vite dev server proxies `/admin-api/*` to `localhost:8001` inside container
- UI calls: `http://localhost:5173/admin-api/api/...` → proxied to `:8001`

**Production (docker run):**
- Container serves UI and APIs together
- Browser runs inside container or as request from host
- UI calls: `http://localhost:8001/api/...` directly (both in same container)
- Agents from external networks call: `http://<container-host>:58000/api/...` with token auth
