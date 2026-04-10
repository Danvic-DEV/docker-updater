from docker import DockerClient
from docker.errors import DockerException, NotFound
from docker.models.containers import Container


def execute_update(target_ref: str, source_type: str, target_container_name: str | None = None) -> tuple[bool, list[str]]:
    logs: list[str] = [f"Starting update for {target_ref} (source={source_type})"]

    if source_type != "registry":
        logs.append("Git-based deployment is not supported")
        return False, logs

    # target_ref format: "image:tag" or "image" (implying latest)
    # If a target container name is provided, only that container is replaced.
    # Otherwise, all containers on this host using the image name are replaced.
    parts = target_ref.split(":", 1)
    image_name = parts[0]

    try:
        client = DockerClient(base_url="unix://var/run/docker.sock")

        # --- 1. Pull new image ---
        logs.append(f"Pulling {target_ref} from registry")
        new_image = client.images.pull(target_ref)
        logs.append(f"Pulled image id={new_image.short_id}")

        # --- 2. Find containers to replace ---
        candidates: list[Container] = []
        all_containers = client.containers.list(all=True)

        if target_container_name:
            for container in all_containers:
                if container.name == target_container_name:
                    candidates.append(container)
                    break
            if not candidates:
                logs.append(f"Target container not found: {target_container_name}")
                return False, logs
        else:
            for container in all_containers:
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
            network_mode = host_config.get("NetworkMode")

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
            labels = config.get("Labels") or {}
            command = config.get("Cmd")
            entrypoint = config.get("Entrypoint")
            user = config.get("User") or None
            working_dir = config.get("WorkingDir") or None
            hostname = config.get("Hostname") or None
            domainname = config.get("Domainname") or None
            tty = bool(config.get("Tty", False))
            stdin_open = bool(config.get("OpenStdin", False))
            stop_signal = config.get("StopSignal") or None

            extra_hosts = host_config.get("ExtraHosts") or None
            dns = host_config.get("Dns") or None
            dns_search = host_config.get("DnsSearch") or None
            privileged = bool(host_config.get("Privileged", False))
            read_only = bool(host_config.get("ReadonlyRootfs", False))
            cap_add = host_config.get("CapAdd") or None
            cap_drop = host_config.get("CapDrop") or None
            security_opt = host_config.get("SecurityOpt") or None
            tmpfs = host_config.get("Tmpfs") or None
            shm_size = host_config.get("ShmSize") or None
            sysctls = host_config.get("Sysctls") or None
            init = host_config.get("Init")

            run_kwargs = {
                "image": target_ref,
                "name": c_name,
                "detach": True,
                "environment": env,
                "labels": labels,
                "command": command,
                "entrypoint": entrypoint,
                "user": user,
                "working_dir": working_dir,
                "hostname": hostname,
                "domainname": domainname,
                "ports": port_bindings,
                "volumes": volumes,
                "restart_policy": restart_policy if restart_policy.get("Name") else None,
                "tty": tty,
                "stdin_open": stdin_open,
                "stop_signal": stop_signal,
                "extra_hosts": extra_hosts,
                "dns": dns,
                "dns_search": dns_search,
                "privileged": privileged,
                "read_only": read_only,
                "cap_add": cap_add,
                "cap_drop": cap_drop,
                "security_opt": security_opt,
                "tmpfs": tmpfs,
                "shm_size": shm_size,
                "sysctls": sysctls,
            }
            if init is not None:
                run_kwargs["init"] = bool(init)

            if network_mode and network_mode not in {"default", "bridge"}:
                run_kwargs["network_mode"] = network_mode
            elif network_names:
                run_kwargs["network"] = network_names[0]

            new_container = client.containers.run(**run_kwargs)

            # Attach additional networks beyond the first
            if not network_mode or network_mode in {"default", "bridge"}:
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
