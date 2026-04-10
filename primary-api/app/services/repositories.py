from datetime import UTC, datetime, timedelta
import hashlib
import secrets
import time
from typing import Any

import psycopg
from psycopg.rows import dict_row

from app.core.config import settings
from app.models.domain import Agent, JobStatus, UpdateJob
from app.services.docker_inspector import has_update_for_remote_image


def _normalize_dsn(database_url: str) -> str:
    if database_url.startswith("postgresql+psycopg://"):
        return database_url.replace("postgresql+psycopg://", "postgresql://", 1)
    return database_url


class PostgresStore:
    def __init__(self) -> None:
        self._dsn = _normalize_dsn(settings.database_url)

    def _connect(self) -> psycopg.Connection[Any]:
        last_error: Exception | None = None
        for _ in range(30):
            try:
                return psycopg.connect(self._dsn)
            except psycopg.OperationalError as exc:
                last_error = exc
                time.sleep(1)
        if last_error is not None:
            raise last_error
        raise RuntimeError("Failed to connect to database")

    def ping(self) -> bool:
        try:
            with psycopg.connect(self._dsn, connect_timeout=2) as conn:
                conn.execute("SELECT 1")
            return True
        except psycopg.OperationalError:
            return False

    def init_db(self) -> None:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS agents (
                        agent_id TEXT PRIMARY KEY,
                        name TEXT NOT NULL,
                        status TEXT NOT NULL,
                        last_heartbeat TIMESTAMPTZ NOT NULL,
                        capabilities JSONB NOT NULL DEFAULT '{}'::jsonb
                    )
                    """
                )
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS update_jobs (
                        job_id TEXT PRIMARY KEY,
                        target_ref TEXT NOT NULL,
                        target_container_name TEXT,
                        source_type TEXT NOT NULL,
                        target_agent_id TEXT NOT NULL REFERENCES agents(agent_id),
                        status TEXT NOT NULL,
                        created_at TIMESTAMPTZ NOT NULL,
                        updated_at TIMESTAMPTZ NOT NULL,
                        logs TEXT[] NOT NULL DEFAULT '{}'
                    )
                    """
                )
                cur.execute("ALTER TABLE update_jobs ADD COLUMN IF NOT EXISTS target_container_name TEXT")
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS agent_tokens (
                        token_hash TEXT PRIMARY KEY,
                        agent_id TEXT NOT NULL REFERENCES agents(agent_id) ON DELETE CASCADE,
                        created_at TIMESTAMPTZ NOT NULL,
                        last_used_at TIMESTAMPTZ NOT NULL,
                        revoked BOOLEAN NOT NULL DEFAULT FALSE
                    )
                    """
                )
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS enrollment_codes (
                        code_hash TEXT PRIMARY KEY,
                        created_at TIMESTAMPTZ NOT NULL,
                        expires_at TIMESTAMPTZ NOT NULL,
                        revoked BOOLEAN NOT NULL DEFAULT FALSE
                    )
                    """
                )
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS container_inventory (
                        container_name TEXT PRIMARY KEY,
                        agent_id TEXT NOT NULL DEFAULT 'primary-local-agent',
                        container_id TEXT NOT NULL,
                        image_ref TEXT NOT NULL,
                        image_id TEXT NOT NULL,
                        status TEXT NOT NULL,
                        has_update BOOLEAN NOT NULL,
                        details JSONB NOT NULL DEFAULT '{}'::jsonb,
                        first_seen TIMESTAMPTZ NOT NULL,
                        last_seen TIMESTAMPTZ NOT NULL,
                        last_changed TIMESTAMPTZ NOT NULL,
                        observation_count INTEGER NOT NULL DEFAULT 0,
                        is_active BOOLEAN NOT NULL DEFAULT TRUE
                    )
                    """
                )
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS container_inventory_history (
                        id BIGSERIAL PRIMARY KEY,
                        container_name TEXT NOT NULL,
                        agent_id TEXT NOT NULL DEFAULT 'primary-local-agent',
                        container_id TEXT NOT NULL,
                        image_ref TEXT NOT NULL,
                        image_id TEXT NOT NULL,
                        status TEXT NOT NULL,
                        has_update BOOLEAN NOT NULL,
                        details JSONB NOT NULL DEFAULT '{}'::jsonb,
                        recorded_at TIMESTAMPTZ NOT NULL,
                        event_type TEXT NOT NULL
                    )
                    """
                )
                cur.execute("ALTER TABLE container_inventory ADD COLUMN IF NOT EXISTS agent_id TEXT NOT NULL DEFAULT 'primary-local-agent'")
                cur.execute("ALTER TABLE container_inventory_history ADD COLUMN IF NOT EXISTS agent_id TEXT NOT NULL DEFAULT 'primary-local-agent'")

    def _hash_secret(self, value: str) -> str:
        return hashlib.sha256(value.encode("utf-8")).hexdigest()

    def create_enrollment_code(self, ttl_minutes: int) -> tuple[str, datetime]:
        now = datetime.now(UTC)
        expires_at = now + timedelta(minutes=ttl_minutes)
        code = secrets.token_urlsafe(24)
        code_hash = self._hash_secret(code)

        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO enrollment_codes (code_hash, created_at, expires_at, revoked)
                    VALUES (%s, %s, %s, FALSE)
                    """,
                    (code_hash, now, expires_at),
                )

        return code, expires_at

    def consume_enrollment_code(self, code: str) -> bool:
        code_hash = self._hash_secret(code)
        with self._connect() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    """
                    UPDATE enrollment_codes
                    SET revoked = TRUE
                    WHERE code_hash = %s
                      AND revoked = FALSE
                      AND expires_at > NOW()
                    RETURNING expires_at
                    """,
                    (code_hash,),
                )
                row = cur.fetchone()
                return row is not None

    def issue_agent_token(self, agent_id: str) -> str:
        now = datetime.now(UTC)
        token = secrets.token_urlsafe(32)
        token_hash = self._hash_secret(token)
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO agent_tokens (token_hash, agent_id, created_at, last_used_at, revoked)
                    VALUES (%s, %s, %s, %s, FALSE)
                    """,
                    (token_hash, agent_id, now, now),
                )
        return token

    def get_agent_id_for_token(self, token: str) -> str | None:
        token_hash = self._hash_secret(token)
        with self._connect() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    """
                    SELECT agent_id
                    FROM agent_tokens
                    WHERE token_hash = %s AND revoked = FALSE
                    """,
                    (token_hash,),
                )
                row = cur.fetchone()
                return row["agent_id"] if row else None

    def touch_agent_token(self, token: str) -> None:
        token_hash = self._hash_secret(token)
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE agent_tokens
                    SET last_used_at = NOW()
                    WHERE token_hash = %s
                    """,
                    (token_hash,),
                )

    def _agent_from_row(self, row: dict[str, Any]) -> Agent:
        return Agent(
            agent_id=row["agent_id"],
            name=row["name"],
            status=row["status"],
            last_heartbeat=row["last_heartbeat"],
            capabilities=row["capabilities"] or {},
        )

    def _job_from_row(self, row: dict[str, Any]) -> UpdateJob:
        return UpdateJob(
            job_id=row["job_id"],
            target_ref=row["target_ref"],
            target_container_name=row.get("target_container_name"),
            source_type=row["source_type"],
            target_agent_id=row["target_agent_id"],
            status=row["status"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            logs=row["logs"] or [],
        )

    def upsert_agent(self, agent: Agent) -> Agent:
        with self._connect() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    """
                    INSERT INTO agents (agent_id, name, status, last_heartbeat, capabilities)
                    VALUES (%s, %s, %s, %s, %s::jsonb)
                    ON CONFLICT (agent_id)
                    DO UPDATE SET
                        name = EXCLUDED.name,
                        status = EXCLUDED.status,
                        last_heartbeat = EXCLUDED.last_heartbeat,
                        capabilities = EXCLUDED.capabilities
                    RETURNING *
                    """,
                    (
                        agent.agent_id,
                        agent.name,
                        agent.status,
                        agent.last_heartbeat,
                        psycopg.types.json.Jsonb(agent.capabilities),
                    ),
                )
                row = cur.fetchone()
                if not row:
                    raise RuntimeError("Failed to upsert agent")
                return self._agent_from_row(row)

    def get_agent(self, agent_id: str) -> Agent | None:
        with self._connect() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute("SELECT * FROM agents WHERE agent_id = %s", (agent_id,))
                row = cur.fetchone()
                return self._agent_from_row(row) if row else None

    def list_agents(self) -> list[Agent]:
        with self._connect() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute("SELECT * FROM agents ORDER BY name ASC")
                rows = cur.fetchall()
                return [self._agent_from_row(row) for row in rows]

    def create_job(self, job: UpdateJob) -> UpdateJob:
        with self._connect() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    """
                    INSERT INTO update_jobs (
                        job_id, target_ref, target_container_name, source_type, target_agent_id, status, created_at, updated_at, logs
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING *
                    """,
                    (
                        job.job_id,
                        job.target_ref,
                        job.target_container_name,
                        job.source_type,
                        job.target_agent_id,
                        job.status,
                        job.created_at,
                        job.updated_at,
                        job.logs,
                    ),
                )
                row = cur.fetchone()
                if not row:
                    raise RuntimeError("Failed to create job")
                return self._job_from_row(row)

    def get_job(self, job_id: str) -> UpdateJob | None:
        with self._connect() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute("SELECT * FROM update_jobs WHERE job_id = %s", (job_id,))
                row = cur.fetchone()
                return self._job_from_row(row) if row else None

    def list_jobs(self) -> list[UpdateJob]:
        with self._connect() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute("SELECT * FROM update_jobs ORDER BY created_at DESC")
                rows = cur.fetchall()
                return [self._job_from_row(row) for row in rows]

    def next_queued_job_for_agent(self, agent_id: str) -> UpdateJob | None:
        with self._connect() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    """
                    SELECT job_id
                    FROM update_jobs
                    WHERE target_agent_id = %s AND status = 'queued'
                    ORDER BY created_at ASC
                    LIMIT 1
                    FOR UPDATE SKIP LOCKED
                    """,
                    (agent_id,),
                )
                candidate = cur.fetchone()
                if not candidate:
                    return None

                cur.execute(
                    """
                    UPDATE update_jobs
                    SET status = 'in_progress', updated_at = NOW()
                    WHERE job_id = %s
                    RETURNING *
                    """,
                    (candidate["job_id"],),
                )
                row = cur.fetchone()
                if not row:
                    return None
                return self._job_from_row(row)

    def update_job_status(self, job_id: str, status: JobStatus, log_line: str | None = None) -> UpdateJob | None:
        with self._connect() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    """
                    UPDATE update_jobs
                    SET
                        status = %s,
                        updated_at = NOW(),
                        logs = CASE WHEN %s IS NULL THEN logs ELSE array_append(logs, %s) END
                    WHERE job_id = %s
                    RETURNING *
                    """,
                    (status, log_line, log_line, job_id),
                )
                row = cur.fetchone()
                return self._job_from_row(row) if row else None

    def _append_inventory_history(self, cur: psycopg.Cursor[Any], item: dict[str, Any], event_type: str, now: datetime) -> None:
        cur.execute(
            """
            INSERT INTO container_inventory_history (
                container_name,
                agent_id,
                container_id,
                image_ref,
                image_id,
                status,
                has_update,
                details,
                recorded_at,
                event_type
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s, %s)
            """,
            (
                item["name"],
                item.get("agent_id", "primary-local-agent"),
                item["id"],
                item["image"],
                item.get("image_id", ""),
                item["status"],
                bool(item.get("has_update", False)),
                psycopg.types.json.Jsonb(item.get("details") or {}),
                now,
                event_type,
            ),
        )

    def _inventory_key(self, agent_id: str, container_name: str) -> str:
        return f"{agent_id}:{container_name}"

    def sync_container_inventory(self, agent_id: str, containers: list[dict[str, Any]]) -> None:
        now = datetime.now(UTC)
        seen_names = [self._inventory_key(agent_id, str(item["name"])) for item in containers]

        with self._connect() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                for item in containers:
                    raw_name = str(item["name"])
                    storage_name = self._inventory_key(agent_id, raw_name)
                    has_update = has_update_for_remote_image(str(item["image"]), str(item.get("image_id", "")))
                    details = dict(item.get("details") or {})
                    details["agent_container_name"] = raw_name

                    stored_item = {
                        **item,
                        "name": storage_name,
                        "has_update": has_update,
                        "details": details,
                        "agent_id": agent_id,
                    }

                    cur.execute(
                        """
                        SELECT * FROM container_inventory WHERE container_name = %s
                        """,
                        (storage_name,),
                    )
                    existing = cur.fetchone()

                    if not existing:
                        cur.execute(
                            """
                            INSERT INTO container_inventory (
                                container_name,
                                agent_id,
                                container_id,
                                image_ref,
                                image_id,
                                status,
                                has_update,
                                details,
                                first_seen,
                                last_seen,
                                last_changed,
                                observation_count,
                                is_active
                            )
                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s, %s, %s, 1, TRUE)
                            """,
                            (
                                stored_item["name"],
                                agent_id,
                                stored_item["id"],
                                stored_item["image"],
                                stored_item.get("image_id", ""),
                                stored_item["status"],
                                bool(stored_item.get("has_update", False)),
                                psycopg.types.json.Jsonb(stored_item.get("details") or {}),
                                now,
                                now,
                                now,
                            ),
                        )
                        self._append_inventory_history(cur, stored_item, "discovered", now)
                        continue

                    details_now = stored_item.get("details") or {}
                    changed = (
                        existing["container_id"] != stored_item["id"]
                        or existing["image_ref"] != stored_item["image"]
                        or existing["image_id"] != stored_item.get("image_id", "")
                        or existing["status"] != stored_item["status"]
                        or bool(existing["has_update"]) != bool(stored_item.get("has_update", False))
                        or (existing.get("details") or {}) != details_now
                        or not bool(existing["is_active"])
                    )

                    cur.execute(
                        """
                        UPDATE container_inventory
                        SET
                            agent_id = %s,
                            container_id = %s,
                            image_ref = %s,
                            image_id = %s,
                            status = %s,
                            has_update = %s,
                            details = %s::jsonb,
                            last_seen = %s,
                            last_changed = CASE WHEN %s THEN %s ELSE last_changed END,
                            observation_count = observation_count + 1,
                            is_active = TRUE
                        WHERE container_name = %s
                        """,
                        (
                            agent_id,
                            stored_item["id"],
                            stored_item["image"],
                            stored_item.get("image_id", ""),
                            stored_item["status"],
                            bool(stored_item.get("has_update", False)),
                            psycopg.types.json.Jsonb(details_now),
                            now,
                            changed,
                            now,
                            stored_item["name"],
                        ),
                    )

                    if changed:
                        self._append_inventory_history(cur, stored_item, "changed", now)

                # Mark previously seen containers as missing when they disappear from current discovery.
                if seen_names:
                    cur.execute(
                        """
                        SELECT * FROM container_inventory
                                                WHERE is_active = TRUE
                                                    AND agent_id = %s
                          AND NOT (container_name = ANY(%s))
                        """,
                                                (agent_id, seen_names),
                    )
                else:
                                        cur.execute("SELECT * FROM container_inventory WHERE is_active = TRUE AND agent_id = %s", (agent_id,))

                missing_rows = cur.fetchall()
                for row in missing_rows:
                    snapshot = {
                        "name": row["container_name"],
                        "agent_id": row.get("agent_id", agent_id),
                        "id": row["container_id"],
                        "image": row["image_ref"],
                        "image_id": row["image_id"],
                        "status": "missing",
                        "has_update": bool(row["has_update"]),
                        "details": row.get("details") or {},
                    }
                    self._append_inventory_history(cur, snapshot, "missing", now)

                if seen_names:
                    cur.execute(
                        """
                        UPDATE container_inventory
                        SET is_active = FALSE, last_changed = %s
                                                WHERE is_active = TRUE
                                                    AND agent_id = %s
                          AND NOT (container_name = ANY(%s))
                        """,
                                                (now, agent_id, seen_names),
                    )
                else:
                    cur.execute(
                        """
                        UPDATE container_inventory
                        SET is_active = FALSE, last_changed = %s
                                                WHERE is_active = TRUE
                                                    AND agent_id = %s
                        """,
                                                (now, agent_id),
                    )

    def list_container_inventory(self, include_inactive: bool = True) -> list[dict[str, Any]]:
        with self._connect() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                if include_inactive:
                    cur.execute(
                        """
                        SELECT *
                        FROM container_inventory
                        ORDER BY is_active DESC, has_update DESC, container_name ASC
                        """
                    )
                else:
                    cur.execute(
                        """
                        SELECT *
                        FROM container_inventory
                        WHERE is_active = TRUE
                        ORDER BY has_update DESC, container_name ASC
                        """
                    )
                result: list[dict[str, Any]] = []
                for row in cur.fetchall():
                    item = dict(row)
                    details = item.get("details") or {}
                    display_name = details.get("agent_container_name") or item.get("container_name")
                    item["name"] = display_name
                    item["image"] = item.get("image_ref")
                    item["id"] = item.get("container_id")
                    item["agent_id"] = item.get("agent_id", "primary-local-agent")
                    result.append(item)
                return result
                

    def list_container_inventory_history(self, limit: int = 500) -> list[dict[str, Any]]:
        with self._connect() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    """
                    SELECT *
                    FROM container_inventory_history
                    ORDER BY recorded_at DESC, id DESC
                    LIMIT %s
                    """,
                    (max(1, min(limit, 5000)),),
                )
                return [dict(row) for row in cur.fetchall()]


store = PostgresStore()
