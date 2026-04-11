import logging
from typing import Any

from docker import DockerClient
from docker.errors import DockerException


log = logging.getLogger(__name__)


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
    has_update, _status, _error = check_update_for_remote_image(image_name, local_image_id)
    return has_update


def check_update_for_remote_image(image_name: str, local_image_id: str) -> tuple[bool, str, str | None]:
    """Return (has_update, status, error) for remote image update checks.

    Status values: available, up_to_date, unknown.
    """
    try:
        client = DockerClient(base_url="unix://var/run/docker.sock")
        try:
            registry_data = client.images.get_registry_data(image_name)
        except Exception as exc:
            error = f"registry lookup failed for {image_name}: {exc}"
            log.warning(error)
            return False, "unknown", error

        registry_id = (getattr(registry_data, "id", "") or "").replace("sha256:", "")
        local_id = (local_image_id or "").replace("sha256:", "")
        if not registry_id or not local_id:
            error = f"missing digest for {image_name} (registry_id={bool(registry_id)}, local_id={bool(local_id)})"
            log.warning(error)
            return False, "unknown", error

        has_update = registry_id != local_id
        return has_update, "available" if has_update else "up_to_date", None
    except DockerException as exc:
        error = f"docker error while checking updates for {image_name}: {exc}"
        log.warning(error)
        return False, "unknown", error


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
