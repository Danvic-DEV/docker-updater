from typing import Any

from docker import DockerClient
from docker.errors import DockerException


def _has_update_available(client: DockerClient, image_name: str) -> bool:
    """Check if an updated version of the image is available in the registry."""
    try:
        # Try to get registry data for the image
        image_obj = client.images.get(image_name)
        
        if not image_obj.id:
            return False
            
        # Get the local image's digest (remove sha256: prefix for comparison)
        local_digest = image_obj.id.replace("sha256:", "")
        
        # Try to pull the image's registry metadata without downloading the full image
        try:
            registry_data = image_obj.get_registry_data()
            if registry_data and registry_data.id:
                registry_digest = registry_data.id.replace("sha256:", "")
                # If digests differ, an update is available
                return local_digest != registry_digest
        except Exception:
            # If we can't get registry data, assume no update (or could re-pull to check)
            pass
            
        return False
    except Exception:
        return False


def has_update_for_remote_image(image_name: str, local_image_id: str) -> bool:
    """Check update availability for an image running on an agent host.

    This compares the agent-reported local image id with the current registry id.
    """
    try:
        client = DockerClient(base_url="unix://var/run/docker.sock")
        try:
            registry_data = client.images.get_registry_data(image_name)
        except Exception:
            return False

        registry_id = (getattr(registry_data, "id", "") or "").replace("sha256:", "")
        local_id = (local_image_id or "").replace("sha256:", "")
        if not registry_id or not local_id:
            return False
        return registry_id != local_id
    except DockerException:
        return False


def list_running_containers() -> list[dict[str, Any]]:
    try:
        client = DockerClient(base_url="unix://var/run/docker.sock")
        containers = client.containers.list()
        result = []
        
        for c in containers:
            image_name = c.image.tags[0] if c.image.tags else c.image.short_id
            has_update = _has_update_available(client, image_name)
            attrs = c.attrs
            details = {
                "labels": attrs.get("Config", {}).get("Labels") or {},
                "env": attrs.get("Config", {}).get("Env") or [],
                "cmd": attrs.get("Config", {}).get("Cmd") or [],
                "entrypoint": attrs.get("Config", {}).get("Entrypoint") or [],
                "ports": attrs.get("NetworkSettings", {}).get("Ports") or {},
                "mounts": attrs.get("Mounts") or [],
                "networks": attrs.get("NetworkSettings", {}).get("Networks") or {},
                "restart_policy": attrs.get("HostConfig", {}).get("RestartPolicy") or {},
            }
            
            result.append({
                "name": c.name,
                "image": image_name,
                "id": c.short_id,
                "image_id": c.image.id,
                "status": c.status,
                "has_update": has_update,
                "details": details,
            })
        
        # Sort by has_update (True first), then by name
        result.sort(key=lambda x: (not x["has_update"], x["name"]))
        return result
    except DockerException:
        return []
