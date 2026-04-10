from fastapi import APIRouter

from app.services.docker_inspector import list_running_containers

router = APIRouter(prefix="/api/docker", tags=["docker"])


@router.get("/targets")
def docker_targets() -> list[dict]:
    return list_running_containers()
