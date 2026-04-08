from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import lru_cache
from typing import Any, Protocol
from uuid import uuid4

from psycopg_pool import ConnectionPool

from app.core.config import settings


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _to_iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat()


def _normalize_json_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except Exception:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


@dataclass
class ChatTaskRecord:
    id: str
    user_id: str
    session_id: str
    input_text: str
    status: str
    request_id: str | None
    result_payload: dict[str, Any]
    error_message: str | None
    created_at: datetime
    updated_at: datetime
    started_at: datetime | None
    finished_at: datetime | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "user_id": self.user_id,
            "session_id": self.session_id,
            "input_text": self.input_text,
            "status": self.status,
            "request_id": self.request_id,
            "result": self.result_payload,
            "error_message": self.error_message,
            "created_at": _to_iso(self.created_at),
            "updated_at": _to_iso(self.updated_at),
            "started_at": _to_iso(self.started_at) if self.started_at else None,
            "finished_at": _to_iso(self.finished_at) if self.finished_at else None,
        }


class TaskStore(Protocol):
    def create_chat_task(self, user_id: str, session_id: str, input_text: str, request_id: str | None) -> dict[str, Any]:
        ...

    def get_chat_task(self, user_id: str, task_id: str) -> dict[str, Any] | None:
        ...

    def get_chat_task_any_user(self, task_id: str) -> dict[str, Any] | None:
        ...

    def mark_chat_task_running(self, task_id: str) -> dict[str, Any] | None:
        ...

    def mark_chat_task_succeeded(self, task_id: str, result_payload: dict[str, Any]) -> dict[str, Any] | None:
        ...

    def mark_chat_task_failed(self, task_id: str, error_message: str) -> dict[str, Any] | None:
        ...


class InMemoryTaskStore:
    def __init__(self) -> None:
        self._tasks: dict[str, ChatTaskRecord] = {}

    def create_chat_task(self, user_id: str, session_id: str, input_text: str, request_id: str | None) -> dict[str, Any]:
        now = _utc_now()
        task = ChatTaskRecord(
            id=f"task_{uuid4().hex[:16]}",
            user_id=user_id,
            session_id=session_id,
            input_text=input_text,
            status="queued",
            request_id=request_id,
            result_payload={},
            error_message=None,
            created_at=now,
            updated_at=now,
            started_at=None,
            finished_at=None,
        )
        self._tasks[task.id] = task
        return task.to_dict()

    def get_chat_task(self, user_id: str, task_id: str) -> dict[str, Any] | None:
        task = self._tasks.get(task_id)
        if task is None or task.user_id != user_id:
            return None
        return task.to_dict()

    def get_chat_task_any_user(self, task_id: str) -> dict[str, Any] | None:
        task = self._tasks.get(task_id)
        return task.to_dict() if task else None

    def mark_chat_task_running(self, task_id: str) -> dict[str, Any] | None:
        task = self._tasks.get(task_id)
        if task is None:
            return None
        now = _utc_now()
        task.status = "running"
        task.started_at = now
        task.updated_at = now
        return task.to_dict()

    def mark_chat_task_succeeded(self, task_id: str, result_payload: dict[str, Any]) -> dict[str, Any] | None:
        task = self._tasks.get(task_id)
        if task is None:
            return None
        now = _utc_now()
        task.status = "succeeded"
        task.result_payload = dict(result_payload)
        task.error_message = None
        task.finished_at = now
        task.updated_at = now
        return task.to_dict()

    def mark_chat_task_failed(self, task_id: str, error_message: str) -> dict[str, Any] | None:
        task = self._tasks.get(task_id)
        if task is None:
            return None
        now = _utc_now()
        task.status = "failed"
        task.error_message = error_message
        task.finished_at = now
        task.updated_at = now
        return task.to_dict()


class PostgresTaskStore:
    def __init__(self, dsn: str) -> None:
        self._dsn = dsn.replace("postgresql+psycopg://", "postgresql://")
        self._pool = ConnectionPool(conninfo=self._dsn, min_size=1, max_size=10, timeout=5, open=True)
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS app_chat_tasks (
                        id TEXT PRIMARY KEY,
                        user_id TEXT NOT NULL,
                        session_id TEXT NOT NULL,
                        input_text TEXT NOT NULL,
                        status TEXT NOT NULL,
                        request_id TEXT NULL,
                        result_payload JSONB NOT NULL DEFAULT '{}'::jsonb,
                        error_message TEXT NULL,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                        started_at TIMESTAMPTZ NULL,
                        finished_at TIMESTAMPTZ NULL
                    )
                    """
                )
                cur.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_app_chat_tasks_user_id_created_at
                    ON app_chat_tasks (user_id, created_at DESC)
                    """
                )
            conn.commit()

    def _task_from_row(self, row) -> ChatTaskRecord:
        return ChatTaskRecord(
            id=row[0],
            user_id=row[1],
            session_id=row[2],
            input_text=row[3],
            status=row[4],
            request_id=row[5],
            result_payload=_normalize_json_dict(row[6]),
            error_message=row[7],
            created_at=row[8],
            updated_at=row[9],
            started_at=row[10],
            finished_at=row[11],
        )

    def create_chat_task(self, user_id: str, session_id: str, input_text: str, request_id: str | None) -> dict[str, Any]:
        task_id = f"task_{uuid4().hex[:16]}"
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO app_chat_tasks (id, user_id, session_id, input_text, status, request_id)
                    VALUES (%s, %s, %s, %s, 'queued', %s)
                    RETURNING id, user_id, session_id, input_text, status, request_id, result_payload,
                              error_message, created_at, updated_at, started_at, finished_at
                    """,
                    (task_id, user_id, session_id, input_text, request_id),
                )
                row = cur.fetchone()
            conn.commit()
        return self._task_from_row(row).to_dict()

    def get_chat_task(self, user_id: str, task_id: str) -> dict[str, Any] | None:
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT id, user_id, session_id, input_text, status, request_id, result_payload,
                           error_message, created_at, updated_at, started_at, finished_at
                    FROM app_chat_tasks
                    WHERE id = %s AND user_id = %s
                    """,
                    (task_id, user_id),
                )
                row = cur.fetchone()
        return self._task_from_row(row).to_dict() if row else None

    def get_chat_task_any_user(self, task_id: str) -> dict[str, Any] | None:
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT id, user_id, session_id, input_text, status, request_id, result_payload,
                           error_message, created_at, updated_at, started_at, finished_at
                    FROM app_chat_tasks
                    WHERE id = %s
                    """,
                    (task_id,),
                )
                row = cur.fetchone()
        return self._task_from_row(row).to_dict() if row else None

    def mark_chat_task_running(self, task_id: str) -> dict[str, Any] | None:
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE app_chat_tasks
                    SET status = 'running', started_at = NOW(), updated_at = NOW()
                    WHERE id = %s
                    RETURNING id, user_id, session_id, input_text, status, request_id, result_payload,
                              error_message, created_at, updated_at, started_at, finished_at
                    """,
                    (task_id,),
                )
                row = cur.fetchone()
            conn.commit()
        return self._task_from_row(row).to_dict() if row else None

    def mark_chat_task_succeeded(self, task_id: str, result_payload: dict[str, Any]) -> dict[str, Any] | None:
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE app_chat_tasks
                    SET status = 'succeeded',
                        result_payload = %s::jsonb,
                        error_message = NULL,
                        finished_at = NOW(),
                        updated_at = NOW()
                    WHERE id = %s
                    RETURNING id, user_id, session_id, input_text, status, request_id, result_payload,
                              error_message, created_at, updated_at, started_at, finished_at
                    """,
                    (json.dumps(result_payload, ensure_ascii=False), task_id),
                )
                row = cur.fetchone()
            conn.commit()
        return self._task_from_row(row).to_dict() if row else None

    def mark_chat_task_failed(self, task_id: str, error_message: str) -> dict[str, Any] | None:
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE app_chat_tasks
                    SET status = 'failed',
                        error_message = %s,
                        finished_at = NOW(),
                        updated_at = NOW()
                    WHERE id = %s
                    RETURNING id, user_id, session_id, input_text, status, request_id, result_payload,
                              error_message, created_at, updated_at, started_at, finished_at
                    """,
                    (error_message, task_id),
                )
                row = cur.fetchone()
            conn.commit()
        return self._task_from_row(row).to_dict() if row else None


@lru_cache(maxsize=1)
def get_task_store() -> TaskStore:
    if settings.postgres_url:
        try:
            return PostgresTaskStore(settings.postgres_url)
        except Exception:
            pass
    return InMemoryTaskStore()
