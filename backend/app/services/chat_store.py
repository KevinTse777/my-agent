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


def _normalize_json_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except Exception:
            return []
        return parsed if isinstance(parsed, list) else []
    return []


def _default_title(title: str | None) -> str:
    cleaned = (title or "").strip()
    return cleaned[:80] if cleaned else "新会话"


def _session_title_from_message(message: str) -> str:
    cleaned = " ".join(message.strip().split())
    return cleaned[:30] if cleaned else "新会话"


@dataclass
class ChatSession:
    id: str
    user_id: str
    title: str
    created_at: datetime
    updated_at: datetime

    def to_dict(self) -> dict[str, str]:
        return {
            "id": self.id,
            "user_id": self.user_id,
            "title": self.title,
            "created_at": _to_iso(self.created_at),
            "updated_at": _to_iso(self.updated_at),
        }


@dataclass
class ChatMessage:
    id: int
    session_id: str
    role: str
    content: str
    tools_used: list[Any]
    sources: list[Any]
    created_at: datetime

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "session_id": self.session_id,
            "role": self.role,
            "content": self.content,
            "tools_used": self.tools_used,
            "sources": self.sources,
            "created_at": _to_iso(self.created_at),
        }


class ChatStore(Protocol):
    def create_session(self, user_id: str, title: str | None = None, session_id: str | None = None) -> dict[str, Any]:
        ...

    def ensure_session(self, user_id: str, session_id: str, title: str | None = None) -> dict[str, Any]:
        ...

    def get_session(self, user_id: str, session_id: str) -> dict[str, Any] | None:
        ...

    def list_sessions(self, user_id: str) -> list[dict[str, Any]]:
        ...

    def list_messages(self, user_id: str, session_id: str, limit: int | None = None) -> list[dict[str, Any]]:
        ...

    def append_message(
        self,
        user_id: str,
        session_id: str,
        role: str,
        content: str,
        *,
        tools_used: list[Any] | None = None,
        sources: list[Any] | None = None,
    ) -> dict[str, Any]:
        ...

    def delete_session(self, user_id: str, session_id: str) -> bool:
        ...


class InMemoryChatStore:
    def __init__(self) -> None:
        self._sessions: dict[str, ChatSession] = {}
        self._messages: dict[str, list[ChatMessage]] = {}
        self._message_seq = 1

    def create_session(self, user_id: str, title: str | None = None, session_id: str | None = None) -> dict[str, Any]:
        session_id = session_id or f"sess_{uuid4().hex[:16]}"
        now = _utc_now()
        session = ChatSession(
            id=session_id,
            user_id=user_id,
            title=_default_title(title),
            created_at=now,
            updated_at=now,
        )
        self._sessions[session_id] = session
        self._messages.setdefault(session_id, [])
        return session.to_dict()

    def get_session(self, user_id: str, session_id: str) -> dict[str, Any] | None:
        session = self._sessions.get(session_id)
        if session is None or session.user_id != user_id:
            return None
        return session.to_dict()

    def ensure_session(self, user_id: str, session_id: str, title: str | None = None) -> dict[str, Any]:
        session = self._sessions.get(session_id)
        if session is None:
            return self.create_session(user_id=user_id, title=title, session_id=session_id)
        if session.user_id != user_id:
            raise PermissionError(session_id)
        if title and session.title == "新会话":
            session.title = _default_title(title)
            session.updated_at = _utc_now()
        return session.to_dict()

    def list_sessions(self, user_id: str) -> list[dict[str, Any]]:
        ordered = sorted(
            (item for item in self._sessions.values() if item.user_id == user_id),
            key=lambda item: item.updated_at,
            reverse=True,
        )
        return [session.to_dict() for session in ordered]

    def list_messages(self, user_id: str, session_id: str, limit: int | None = None) -> list[dict[str, Any]]:
        session = self._sessions.get(session_id)
        if session is None:
            raise KeyError(session_id)
        if session.user_id != user_id:
            raise PermissionError(session_id)
        messages = self._messages.get(session_id, [])
        if limit is not None:
            messages = messages[-limit:]
        return [message.to_dict() for message in messages]

    def append_message(
        self,
        user_id: str,
        session_id: str,
        role: str,
        content: str,
        *,
        tools_used: list[Any] | None = None,
        sources: list[Any] | None = None,
    ) -> dict[str, Any]:
        session = self._sessions.get(session_id)
        if session is None:
            session = ChatSession(
                id=session_id,
                user_id=user_id,
                title="新会话",
                created_at=_utc_now(),
                updated_at=_utc_now(),
            )
            self._sessions[session_id] = session
            self._messages.setdefault(session_id, [])
        if session.user_id != user_id:
            raise PermissionError(session_id)
        if role == "user" and session.title == "新会话":
            session.title = _session_title_from_message(content)
        session.updated_at = _utc_now()
        message = ChatMessage(
            id=self._message_seq,
            session_id=session_id,
            role=role,
            content=content,
            tools_used=list(tools_used or []),
            sources=list(sources or []),
            created_at=_utc_now(),
        )
        self._message_seq += 1
        self._messages.setdefault(session_id, []).append(message)
        return message.to_dict()

    def delete_session(self, user_id: str, session_id: str) -> bool:
        session = self._sessions.get(session_id)
        if session is None:
            return False
        if session.user_id != user_id:
            raise PermissionError(session_id)
        self._sessions.pop(session_id, None)
        self._messages.pop(session_id, None)
        return True


class PostgresChatStore:
    def __init__(self, dsn: str) -> None:
        self._dsn = dsn.replace("postgresql+psycopg://", "postgresql://")
        self._pool = ConnectionPool(conninfo=self._dsn, min_size=1, max_size=10, timeout=5, open=True)
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS app_chat_sessions (
                        id TEXT PRIMARY KEY,
                        user_id TEXT NOT NULL,
                        title TEXT NOT NULL,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    )
                    """
                )
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS app_chat_messages (
                        id BIGSERIAL PRIMARY KEY,
                        session_id TEXT NOT NULL REFERENCES app_chat_sessions(id) ON DELETE CASCADE,
                        role TEXT NOT NULL,
                        content TEXT NOT NULL,
                        tools_used JSONB NOT NULL DEFAULT '[]'::jsonb,
                        sources JSONB NOT NULL DEFAULT '[]'::jsonb,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    )
                    """
                )
                cur.execute("ALTER TABLE app_chat_sessions ADD COLUMN IF NOT EXISTS user_id TEXT")
                cur.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_app_chat_messages_session_id_id
                    ON app_chat_messages (session_id, id)
                    """
                )
                cur.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_app_chat_sessions_user_id_updated_at
                    ON app_chat_sessions (user_id, updated_at DESC)
                    """
                )
            conn.commit()

    def _session_from_row(self, row) -> ChatSession:
        return ChatSession(id=row[0], user_id=row[1], title=row[2], created_at=row[3], updated_at=row[4])

    def _message_from_row(self, row) -> ChatMessage:
        return ChatMessage(
            id=row[0],
            session_id=row[1],
            role=row[2],
            content=row[3],
            tools_used=_normalize_json_list(row[4]),
            sources=_normalize_json_list(row[5]),
            created_at=row[6],
        )

    def create_session(self, user_id: str, title: str | None = None, session_id: str | None = None) -> dict[str, Any]:
        session_id = session_id or f"sess_{uuid4().hex[:16]}"
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO app_chat_sessions (id, user_id, title)
                    VALUES (%s, %s, %s)
                    RETURNING id, user_id, title, created_at, updated_at
                    """,
                    (session_id, user_id, _default_title(title)),
                )
                row = cur.fetchone()
            conn.commit()
        return self._session_from_row(row).to_dict()

    def get_session(self, user_id: str, session_id: str) -> dict[str, Any] | None:
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT id, user_id, title, created_at, updated_at
                    FROM app_chat_sessions
                    WHERE id = %s AND user_id = %s
                    """,
                    (session_id, user_id),
                )
                row = cur.fetchone()
        return self._session_from_row(row).to_dict() if row else None

    def ensure_session(self, user_id: str, session_id: str, title: str | None = None) -> dict[str, Any]:
        session = self.get_session(user_id, session_id)
        if session:
            return session
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT user_id FROM app_chat_sessions WHERE id = %s", (session_id,))
                owner = cur.fetchone()
                if owner and owner[0] != user_id:
                    raise PermissionError(session_id)
            conn.commit()
        return self.create_session(user_id=user_id, title=title, session_id=session_id)

    def list_sessions(self, user_id: str) -> list[dict[str, Any]]:
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT id, user_id, title, created_at, updated_at
                    FROM app_chat_sessions
                    WHERE user_id = %s
                    ORDER BY updated_at DESC
                    """,
                    (user_id,),
                )
                rows = cur.fetchall()
        return [self._session_from_row(row).to_dict() for row in rows]

    def list_messages(self, user_id: str, session_id: str, limit: int | None = None) -> list[dict[str, Any]]:
        if self.get_session(user_id, session_id) is None:
            with self._pool.connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT 1 FROM app_chat_sessions WHERE id = %s", (session_id,))
                    if cur.fetchone():
                        raise PermissionError(session_id)
            raise KeyError(session_id)
        sql = """
            SELECT id, session_id, role, content, tools_used, sources, created_at
            FROM app_chat_messages
            WHERE session_id = %s
            ORDER BY id ASC
        """
        params: list[Any] = [session_id]
        if limit is not None:
            sql += " LIMIT %s"
            params.append(limit)
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, tuple(params))
                rows = cur.fetchall()
        return [self._message_from_row(row).to_dict() for row in rows]

    def append_message(
        self,
        user_id: str,
        session_id: str,
        role: str,
        content: str,
        *,
        tools_used: list[Any] | None = None,
        sources: list[Any] | None = None,
    ) -> dict[str, Any]:
        self.ensure_session(user_id=user_id, session_id=session_id)
        title = _session_title_from_message(content) if role == "user" else None
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                if role == "user":
                    cur.execute(
                        """
                        UPDATE app_chat_sessions
                        SET title = CASE WHEN title = '新会话' THEN %s ELSE title END,
                            updated_at = NOW()
                        WHERE id = %s AND user_id = %s
                        """,
                        (_default_title(title), session_id, user_id),
                    )
                else:
                    cur.execute(
                        """
                        UPDATE app_chat_sessions
                        SET updated_at = NOW()
                        WHERE id = %s AND user_id = %s
                        """,
                        (session_id, user_id),
                    )
                cur.execute(
                    """
                    INSERT INTO app_chat_messages (session_id, role, content, tools_used, sources)
                    VALUES (%s, %s, %s, %s::jsonb, %s::jsonb)
                    RETURNING id, session_id, role, content, tools_used, sources, created_at
                    """,
                    (
                        session_id,
                        role,
                        content,
                        json.dumps(list(tools_used or []), ensure_ascii=False),
                        json.dumps(list(sources or []), ensure_ascii=False),
                    ),
                )
                row = cur.fetchone()
            conn.commit()
        return self._message_from_row(row).to_dict()

    def delete_session(self, user_id: str, session_id: str) -> bool:
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT user_id FROM app_chat_sessions WHERE id = %s", (session_id,))
                owner = cur.fetchone()
                if owner is None:
                    return False
                if owner[0] != user_id:
                    raise PermissionError(session_id)
                cur.execute("DELETE FROM app_chat_sessions WHERE id = %s AND user_id = %s", (session_id, user_id))
                deleted = cur.rowcount > 0
            conn.commit()
        return deleted


@lru_cache(maxsize=1)
def get_chat_store() -> ChatStore:
    validate_runtime_configuration()
    if settings.postgres_url:
        try:
            return PostgresChatStore(settings.postgres_url)
        except Exception:
            pass
    return InMemoryChatStore()
