from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import lru_cache
from typing import Protocol
from uuid import uuid4

from psycopg_pool import ConnectionPool

from app.core.config import settings, validate_runtime_configuration


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class UserRecord:
    id: str
    email: str
    username: str
    password_hash: str
    status: str
    created_at: datetime
    updated_at: datetime

    def public_dict(self) -> dict[str, str]:
        return {
            "id": self.id,
            "email": self.email,
            "username": self.username,
            "status": self.status,
            "created_at": self.created_at.astimezone(timezone.utc).isoformat(),
            "updated_at": self.updated_at.astimezone(timezone.utc).isoformat(),
        }


@dataclass
class RefreshSessionRecord:
    id: str
    user_id: str
    refresh_token_hash: str
    status: str
    expires_at: datetime
    created_at: datetime
    updated_at: datetime


class AuthStore(Protocol):
    def create_user(self, email: str, username: str, password_hash: str) -> UserRecord:
        ...

    def get_user_by_email(self, email: str) -> UserRecord | None:
        ...

    def get_user_by_id(self, user_id: str) -> UserRecord | None:
        ...

    def create_refresh_session(
        self,
        user_id: str,
        refresh_token_hash: str,
        expires_at: datetime,
    ) -> RefreshSessionRecord:
        ...

    def get_refresh_session(self, session_id: str) -> RefreshSessionRecord | None:
        ...

    def update_refresh_session_hash(self, session_id: str, refresh_token_hash: str) -> bool:
        ...

    def revoke_refresh_session(self, session_id: str) -> bool:
        ...


class InMemoryAuthStore:
    def __init__(self) -> None:
        self._users_by_id: dict[str, UserRecord] = {}
        self._user_ids_by_email: dict[str, str] = {}
        self._refresh_sessions: dict[str, RefreshSessionRecord] = {}

    def create_user(self, email: str, username: str, password_hash: str) -> UserRecord:
        email_key = email.strip().lower()
        if email_key in self._user_ids_by_email:
            raise ValueError("Email already exists")

        now = _utc_now()
        user = UserRecord(
            id=f"user_{uuid4().hex[:16]}",
            email=email_key,
            username=username.strip(),
            password_hash=password_hash,
            status="active",
            created_at=now,
            updated_at=now,
        )
        self._users_by_id[user.id] = user
        self._user_ids_by_email[email_key] = user.id
        return user

    def get_user_by_email(self, email: str) -> UserRecord | None:
        user_id = self._user_ids_by_email.get(email.strip().lower())
        return self._users_by_id.get(user_id) if user_id else None

    def get_user_by_id(self, user_id: str) -> UserRecord | None:
        return self._users_by_id.get(user_id)

    def create_refresh_session(
        self,
        user_id: str,
        refresh_token_hash: str,
        expires_at: datetime,
    ) -> RefreshSessionRecord:
        now = _utc_now()
        record = RefreshSessionRecord(
            id=f"usess_{uuid4().hex[:16]}",
            user_id=user_id,
            refresh_token_hash=refresh_token_hash,
            status="active",
            expires_at=expires_at,
            created_at=now,
            updated_at=now,
        )
        self._refresh_sessions[record.id] = record
        return record

    def get_refresh_session(self, session_id: str) -> RefreshSessionRecord | None:
        return self._refresh_sessions.get(session_id)

    def update_refresh_session_hash(self, session_id: str, refresh_token_hash: str) -> bool:
        record = self._refresh_sessions.get(session_id)
        if record is None:
            return False
        record.refresh_token_hash = refresh_token_hash
        record.updated_at = _utc_now()
        return True

    def revoke_refresh_session(self, session_id: str) -> bool:
        record = self._refresh_sessions.get(session_id)
        if record is None:
            return False
        record.status = "revoked"
        record.updated_at = _utc_now()
        return True


class PostgresAuthStore:
    def __init__(self, dsn: str) -> None:
        self._dsn = dsn.replace("postgresql+psycopg://", "postgresql://")
        self._pool = ConnectionPool(conninfo=self._dsn, min_size=1, max_size=10, timeout=5, open=True)
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS app_users (
                        id TEXT PRIMARY KEY,
                        email TEXT NOT NULL UNIQUE,
                        username TEXT NOT NULL,
                        password_hash TEXT NOT NULL,
                        status TEXT NOT NULL DEFAULT 'active',
                        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    )
                    """
                )
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS app_user_sessions (
                        id TEXT PRIMARY KEY,
                        user_id TEXT NOT NULL REFERENCES app_users(id) ON DELETE CASCADE,
                        refresh_token_hash TEXT NOT NULL,
                        status TEXT NOT NULL DEFAULT 'active',
                        expires_at TIMESTAMPTZ NOT NULL,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    )
                    """
                )
                cur.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_app_user_sessions_user_id
                    ON app_user_sessions (user_id)
                    """
                )
            conn.commit()

    def _user_from_row(self, row) -> UserRecord:
        return UserRecord(
            id=row[0],
            email=row[1],
            username=row[2],
            password_hash=row[3],
            status=row[4],
            created_at=row[5],
            updated_at=row[6],
        )

    def _refresh_from_row(self, row) -> RefreshSessionRecord:
        return RefreshSessionRecord(
            id=row[0],
            user_id=row[1],
            refresh_token_hash=row[2],
            status=row[3],
            expires_at=row[4],
            created_at=row[5],
            updated_at=row[6],
        )

    def create_user(self, email: str, username: str, password_hash: str) -> UserRecord:
        user_id = f"user_{uuid4().hex[:16]}"
        email_key = email.strip().lower()
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO app_users (id, email, username, password_hash)
                    VALUES (%s, %s, %s, %s)
                    RETURNING id, email, username, password_hash, status, created_at, updated_at
                    """,
                    (user_id, email_key, username.strip(), password_hash),
                )
                row = cur.fetchone()
            conn.commit()
        return self._user_from_row(row)

    def get_user_by_email(self, email: str) -> UserRecord | None:
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT id, email, username, password_hash, status, created_at, updated_at
                    FROM app_users
                    WHERE email = %s
                    """,
                    (email.strip().lower(),),
                )
                row = cur.fetchone()
        return self._user_from_row(row) if row else None

    def get_user_by_id(self, user_id: str) -> UserRecord | None:
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT id, email, username, password_hash, status, created_at, updated_at
                    FROM app_users
                    WHERE id = %s
                    """,
                    (user_id,),
                )
                row = cur.fetchone()
        return self._user_from_row(row) if row else None

    def create_refresh_session(
        self,
        user_id: str,
        refresh_token_hash: str,
        expires_at: datetime,
    ) -> RefreshSessionRecord:
        session_id = f"usess_{uuid4().hex[:16]}"
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO app_user_sessions (id, user_id, refresh_token_hash, expires_at)
                    VALUES (%s, %s, %s, %s)
                    RETURNING id, user_id, refresh_token_hash, status, expires_at, created_at, updated_at
                    """,
                    (session_id, user_id, refresh_token_hash, expires_at),
                )
                row = cur.fetchone()
            conn.commit()
        return self._refresh_from_row(row)

    def get_refresh_session(self, session_id: str) -> RefreshSessionRecord | None:
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT id, user_id, refresh_token_hash, status, expires_at, created_at, updated_at
                    FROM app_user_sessions
                    WHERE id = %s
                    """,
                    (session_id,),
                )
                row = cur.fetchone()
        return self._refresh_from_row(row) if row else None

    def update_refresh_session_hash(self, session_id: str, refresh_token_hash: str) -> bool:
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE app_user_sessions
                    SET refresh_token_hash = %s, updated_at = NOW()
                    WHERE id = %s
                    """,
                    (refresh_token_hash, session_id),
                )
                updated = cur.rowcount > 0
            conn.commit()
        return updated

    def revoke_refresh_session(self, session_id: str) -> bool:
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE app_user_sessions
                    SET status = 'revoked', updated_at = NOW()
                    WHERE id = %s
                    """,
                    (session_id,),
                )
                updated = cur.rowcount > 0
            conn.commit()
        return updated


@lru_cache(maxsize=1)
def get_auth_store() -> AuthStore:
    validate_runtime_configuration()
    if settings.postgres_url:
        try:
            return PostgresAuthStore(settings.postgres_url)
        except Exception:
            pass
    return InMemoryAuthStore()


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
