# Docker Updater

Monorepo for a Docker update orchestration system with:
- Primary control plane API: FastAPI + PostgreSQL
- Primary web UI: React + Vite
- Remote agent: Python polling worker

## Quick Start

1. Copy environment files:

```bash
cp primary-api/.env.example primary-api/.env
cp agent/.env.example agent/.env
cp primary-web/.env.example primary-web/.env
```

2. Start local stack:

```bash
docker compose up --build
```

3. Open:
- API docs: http://localhost:8000/docs
- Web UI: http://localhost:5173

## Current Status

Initial implementation scaffold with:
- Agent registration and heartbeat endpoints
- In-memory job queue for manual update requests
- Agent polling and simulated update execution
- Basic dashboard for agents and jobs

## GHCR Auto Build

GitHub Actions publish separate images to GHCR with path-based triggers:
- Primary image: `ghcr.io/<owner>/docker-updater-primary`
	- Triggered by changes under `primary/`, `primary-api/`, `primary-web/`, and `agent/`.
- Agent image: `ghcr.io/<owner>/docker-updater-agent`
	- Triggered by changes under `agent/`.

Workflows:
- `.github/workflows/build-primary.yml`
- `.github/workflows/build-agent.yml`
