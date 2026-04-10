from docker import DockerClient
from docker.errors import DockerException, NotFound
from docker.models.containers import Container


def execute_update(target_ref: str, source_type: str) -> tuple[bool, list[str]]:
    logs: list[str] = [f"Starting update for {target_ref} (source={source_type})"]

    if source_type != "registry":
        logs.append("Git-based deployment is not supported")
        return False, logs

    # target_ref format: "image:tag" or "image" (implying latest)
    # Find containers currently using this image name (any tag), then replace them
    # with the freshly pulled image.
    parts = target_ref.split(":", 1)
    image_name = parts[0]

    try:
        client = DockerClient(base_url="unix://var/run/docker.sock")

        # --- 1. Pull new image ---
        logs.append(f"Pulling {target_ref} from registry")
        new_image = client.images.pull(target_ref)
        logs.append(f"Pulled image id={new_image.short_id}")

        # --- 2. Find running containers that use this image ---
        candidates: list[Container] = []
        for container in client.containers.list(all=True):
            img_name = container.image.tags[0] if container.image.tags else ""
            if img_name.split(":")[0] == image_name or container.image.short_id == new_image.short_id:
                candidates.append(container)

        if not candidates:
            logs.append("No running containers found for this image — image pulled and cached")
            return True, logs

        for container in candidates:
            c_name = container.name
            logs.append(f"Replacing container {c_name}")

            # Capture runtime config needed to recreate
            attrs = container.attrs
            host_config = attrs["HostConfig"]
            config = attrs["Config"]
            network_settings = attrs["NetworkSettings"]

            # Build restart policy
            restart_policy = host_config.get("RestartPolicy", {})

            # Collect network names (skip default bridge added implicitly)
            network_names = [
                n for n in network_settings.get("Networks", {}).keys()
                if n != "bridge"
            ]

            # --- 3. Stop old container ---
            if container.status == "running":
                logs.append(f"Stopping {c_name}")
                container.stop(timeout=30)
                logs.append(f"Stopped {c_name}")

            # --- 4. Remove old container ---
            container.remove()
            logs.append(f"Removed old container {c_name}")

            # --- 5. Start new container with same config ---
            port_bindings = host_config.get("PortBindings") or {}
            volumes = host_config.get("Binds") or []
            env = config.get("Env") or []

            new_container = client.containers.run(
                image=target_ref,
                name=c_name,
                detach=True,
                environment=env,
                ports=port_bindings,
                volumes=volumes,
                restart_policy=restart_policy if restart_policy.get("Name") else None,
                network=network_names[0] if network_names else None,
            )

            # Attach additional networks beyond the first
            for net_name in network_names[1:]:
                network = client.networks.get(net_name)
                network.connect(new_container)

            logs.append(f"Started new container {c_name} id={new_container.short_id}")

        return True, logs

    except NotFound as exc:
        logs.append(f"Resource not found: {exc}")
        return False, logs
    except DockerException as exc:
        logs.append(f"Docker error: {exc}")
        return False, logs
