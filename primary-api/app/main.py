from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.agents import router as agents_router
from app.api.docker_targets import router as docker_router
from app.api.health import router as health_router
from app.api.jobs import router as jobs_router
from app.services.repositories import store

app = FastAPI(title="Docker Updater Primary API", version="0.1.0")


@app.on_event("startup")
def on_startup() -> None:
    store.init_db()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_router)
app.include_router(agents_router)
app.include_router(jobs_router)
app.include_router(docker_router)
