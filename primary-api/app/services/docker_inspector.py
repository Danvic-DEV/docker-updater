from docker import DockerClient
from docker.errors import DockerException


def _has_update_available(client: DockerClient, image_name: str, current_digest: str) -> bool:
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


def list_running_containers() -> list[dict]:
    try:
        client = DockerClient(base_url="unix://var/run/docker.sock")
        containers = client.containers.list()
        result = []
        
        for c in containers:
            image_name = c.image.tags[0] if c.image.tags else c.image.short_id
            has_update = _has_update_available(client, image_name, c.image.id)
            
            result.append({
                "name": c.name,
                "image": image_name,
                "id": c.short_id,
                "status": c.status,
                "has_update": has_update,
            })
        
        # Sort by has_update (True first), then by name
        result.sort(key=lambda x: (not x["has_update"], x["name"]))
        return result
    except DockerException:
        return []
