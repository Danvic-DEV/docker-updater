from docker import DockerClient
from docker.errors import DockerException


def list_running_containers() -> list[dict[str, str]]:
    try:
        client = DockerClient(base_url="unix://var/run/docker.sock")
        containers = client.containers.list()
        return [
            {
                "name": c.name,
                "image": c.image.tags[0] if c.image.tags else c.image.short_id,
                "id": c.short_id,
                "status": c.status,
            }
            for c in containers
        ]
    except DockerException:
        return []
