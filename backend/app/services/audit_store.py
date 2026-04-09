from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import lru_cache
from typing import Any, Protocol
from uuid import uuid4

from psycopg_pool import ConnectionPool

from app.core.config import settings, validate_runtime_configuration


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
class AuditLogRecord:
    id: str
    user_id: str | None
    event_type: str
    event_payload: dict[str, Any]
    request_id: str | None
    created_at: datetime

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "user_id": self.user_id,
            "event_type": self.event_type,
            "event_payload": self.event_payload,
            "request_id": self.request_id,
            "created_at": _to_iso(self.created_at),
        }


class AuditStore(Protocol):
    def create_event(
        self,
        *,
        user_id: str | None,
        event_type: str,
        event_payload: dict[str, Any],
        request_id: str | None,
    ) -> dict[str, Any]:
        ...

    def list_events(self, limit: int = 100) -> list[dict[str, Any]]:
        ...


class InMemoryAuditStore:
    def __init__(self) -> None:
        self._events: list[AuditLogRecord] = []

    def create_event(
        self,
        *,
        user_id: str | None,
        event_type: str,
        event_payload: dict[str, Any],
        request_id: str | None,
    ) -> dict[str, Any]:
        event = AuditLogRecord(
            id=f"audit_{uuid4().hex[:16]}",
            user_id=user_id,
            event_type=event_type,
            event_payload=dict(event_payload),
            request_id=request_id,
            created_at=_utc_now(),
        )
        self._events.append(event)
        return event.to_dict()

    def list_events(self, limit: int = 100) -> list[dict[str, Any]]:
        return [event.to_dict() for event in self._events[-limit:]][::-1]


class PostgresAuditStore:
    def __init__(self, dsn: str) -> None:
        self._dsn = dsn.replace("postgresql+psycopg://", "postgresql://")
        self._pool = ConnectionPool(conninfo=self._dsn, min_size=1, max_size=10, timeout=5, open=True)
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS app_audit_logs (
                        id TEXT PRIMARY KEY,
                        user_id TEXT NULL,
                        event_type TEXT NOT NULL,
                        event_payload JSONB NOT NULL DEFAULT '{}'::jsonb,
                        request_id TEXT NULL,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    )
                    """
                )
                cur.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_app_audit_logs_created_at
                    ON app_audit_logs (created_at DESC)
                    """
                )
                cur.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_app_audit_logs_user_id_created_at
                    ON app_audit_logs (user_id, created_at DESC)
                    """
                )
            conn.commit()

    def _event_from_row(self, row) -> AuditLogRecord:
        return AuditLogRecord(
            id=row[0],
            user_id=row[1],
            event_type=row[2],
            event_payload=_normalize_json_dict(row[3]),
            request_id=row[4],
            created_at=row[5],
        )

    def create_event(
        self,
        *,
        user_id: str | None,
        event_type: str,
        event_payload: dict[str, Any],
        request_id: str | None,
    ) -> dict[str, Any]:
        event_id = f"audit_{uuid4().hex[:16]}"
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO app_audit_logs (id, user_id, event_type, event_payload, request_id)
                    VALUES (%s, %s, %s, %s::jsonb, %s)
                    RETURNING id, user_id, event_type, event_payload, request_id, created_at
                    """,
                    (event_id, user_id, event_type, json.dumps(event_payload, ensure_ascii=False), request_id),
                )
                row = cur.fetchone()
            conn.commit()
        return self._event_from_row(row).to_dict()

    def list_events(self, limit: int = 100) -> list[dict[str, Any]]:
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT id, user_id, event_type, event_payload, request_id, created_at
                    FROM app_audit_logs
                    ORDER BY created_at DESC
                    LIMIT %s
                    """,
                    (limit,),
                )
                rows = cur.fetchall()
        return [self._event_from_row(row).to_dict() for row in rows]


@lru_cache(maxsize=1)
def get_audit_store() -> AuditStore:
    validate_runtime_configuration()
    if settings.postgres_url:
        try:
            return PostgresAuditStore(settings.postgres_url)
        except Exception:
            pass
    return InMemoryAuditStore()
