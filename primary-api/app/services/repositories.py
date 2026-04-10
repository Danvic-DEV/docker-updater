from datetime import UTC, datetime, timedelta
import hashlib
import secrets
import time
from typing import Any

import psycopg
from psycopg.rows import dict_row

from app.core.config import settings
from app.models.domain import Agent, JobStatus, UpdateJob


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
                        source_type TEXT NOT NULL,
                        target_agent_id TEXT NOT NULL REFERENCES agents(agent_id),
                        status TEXT NOT NULL,
                        created_at TIMESTAMPTZ NOT NULL,
                        updated_at TIMESTAMPTZ NOT NULL,
                        logs TEXT[] NOT NULL DEFAULT '{}'
                    )
                    """
                )
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
                        job_id, target_ref, source_type, target_agent_id, status, created_at, updated_at, logs
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING *
                    """,
                    (
                        job.job_id,
                        job.target_ref,
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


store = PostgresStore()
