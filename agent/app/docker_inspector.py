from typing import Any

from docker import DockerClient
from docker.errors import DockerException


def list_running_containers() -> list[dict[str, Any]]:
    try:
        client = DockerClient(base_url="unix://var/run/docker.sock")
        containers = client.containers.list()
        result: list[dict[str, Any]] = []

        for c in containers:
            image_name = c.image.tags[0] if c.image.tags else c.image.short_id
            attrs = c.attrs
            details = {
                "labels": attrs.get("Config", {}).get("Labels") or {},
                "ports": attrs.get("NetworkSettings", {}).get("Ports") or {},
                "mounts": attrs.get("Mounts") or [],
                "networks": attrs.get("NetworkSettings", {}).get("Networks") or {},
                "restart_policy": attrs.get("HostConfig", {}).get("RestartPolicy") or {},
            }
            result.append(
                {
                    "name": c.name,
                    "image": image_name,
                    "id": c.short_id,
                    "image_id": c.image.id,
                    "status": c.status,
                    "details": details,
                }
            )

        return result
    except DockerException:
        return []