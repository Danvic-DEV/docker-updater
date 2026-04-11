import logging
import time

from httpx import HTTPError

from app.api_client import PrimaryApiClient
from app.config import settings
from app.docker_inspector import list_running_containers
from app.executor import execute_update

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)


def run() -> None:
    api = PrimaryApiClient()

    # Registration with retry so the agent survives a slow primary startup
    while True:
        try:
            api.register()
            log.info("Registered with primary")
            break
        except HTTPError as exc:
            log.warning("Registration failed (%s), retrying in 5s", exc)
            time.sleep(5)

    while True:
        got_job = False
        try:
            api.heartbeat()
            api.sync_inventory(list_running_containers())
            job = api.pull_next_job()
            if job:
                got_job = True
                job_id = job["job_id"]
                api.report_progress(job_id=job_id, status="in_progress", log_line="Job accepted by agent")
                success, logs = execute_update(job["target_ref"], job["source_type"], job.get("target_container_name"))
                for line in logs:
                    api.report_progress(job_id=job_id, status="in_progress", log_line=line)
                final_status = "completed" if success else "failed"
                api.report_progress(job_id=job_id, status=final_status, log_line=f"Job finished: {final_status}")
        except HTTPError as exc:
            log.warning("Transient API error: %s", exc)

        # Poll immediately if a job was just completed (may be more queued)
        if not got_job:
            time.sleep(settings.poll_interval_seconds)


if __name__ == "__main__":
    run()
