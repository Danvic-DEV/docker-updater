from fastapi import APIRouter

from app.services.docker_inspector import list_running_containers
from app.services.repositories import store

router = APIRouter(prefix="/api/docker", tags=["admin-docker"])


@router.get("/targets")
def docker_targets() -> list[dict]:
    containers = list_running_containers()
    store.sync_container_inventory(containers)
    return [
        {
            "name": item["name"],
            "image": item["image"],
            "id": item["id"],
            "status": item["status"],
            "has_update": item.get("has_update", False),
        }
        for item in containers
    ]


@router.get("/inventory")
def docker_inventory(include_inactive: bool = True) -> list[dict]:
    return store.list_container_inventory(include_inactive=include_inactive)


@router.get("/inventory/history")
def docker_inventory_history(limit: int = 500) -> list[dict]:
    return store.list_container_inventory_history(limit=limit)
