from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.agents import router as agents_router
from app.api.jobs import router as jobs_router
from app.api.admin_agents import router as admin_agents_router
from app.api.admin_jobs import router as admin_jobs_router
from app.api.admin_docker import router as admin_docker_router
from app.api.health import router as health_router
from app.services.repositories import store

# Agent API (port 58000) - exposed, requires per-agent token auth
agent_app = FastAPI(title="Docker Updater Agent API", version="0.1.0")

@agent_app.on_event("startup")
def on_startup_agent() -> None:
    store.init_db()

agent_app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

agent_app.include_router(health_router)
agent_app.include_router(agents_router)
agent_app.include_router(jobs_router)

# Admin API (port 8001) - NOT exposed, only for UI
admin_app = FastAPI(title="Docker Updater Admin API", version="0.1.0")

admin_app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

admin_app.include_router(admin_agents_router)
admin_app.include_router(admin_jobs_router)
admin_app.include_router(admin_docker_router)

# Default export for port 58000
app = agent_app
