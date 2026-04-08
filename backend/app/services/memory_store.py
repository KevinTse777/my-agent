from __future__ import annotations

import json
from typing import Protocol

from psycopg_pool import ConnectionPool
from redis import Redis


class MemoryStore(Protocol):
    def load_context(self, session_id: str) -> list[dict[str, str]]:
        ...

    def append_turn(self, session_id: str, user_input: str, assistant_output: str) -> None:
        ...


class InMemoryStore:
    def __init__(self, max_history_messages: int = 12) -> None:
        self._max_history_messages = max_history_messages
        self._store: dict[str, list[dict[str, str]]] = {}

    def load_context(self, session_id: str) -> list[dict[str, str]]:
        history = self._store.get(session_id, [])
        return history[-self._max_history_messages :]

    def append_turn(self, session_id: str, user_input: str, assistant_output: str) -> None:
        history = self._store.get(session_id, [])
        history.extend(
            [
                {"role": "user", "content": user_input},
                {"role": "assistant", "content": assistant_output},
            ]
        )
        self._store[session_id] = history[-self._max_history_messages :]


class PostgresMemoryStore:
    def __init__(self, dsn: str, max_history_messages: int = 12) -> None:
        self._dsn = dsn.replace("postgresql+psycopg://", "postgresql://")
        self._max_history_messages = max_history_messages
        self._pool = ConnectionPool(
            conninfo=self._dsn,
            min_size=1,
            max_size=10,
            timeout=5,
            open=True,
        )
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS chat_messages (
                        id BIGSERIAL PRIMARY KEY,
                        session_id VARCHAR(128) NOT NULL,
                        role VARCHAR(32) NOT NULL CHECK (role IN ('user', 'assistant')),
                        content TEXT NOT NULL,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    )
                    """
                )
                cur.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_chat_messages_session_created_at
                    ON chat_messages (session_id, created_at DESC)
                    """
                )
            conn.commit()

    def load_context(self, session_id: str) -> list[dict[str, str]]:
        sql = """
            SELECT role, content
            FROM chat_messages
            WHERE session_id = %s
            ORDER BY id DESC
            LIMIT %s
        """
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, (session_id, self._max_history_messages))
                rows = cur.fetchall()
        rows.reverse()
        return [{"role": r[0], "content": r[1]} for r in rows]

    def append_turn(self, session_id: str, user_input: str, assistant_output: str) -> None:
        sql = """
            INSERT INTO chat_messages (session_id, role, content)
            VALUES (%s, %s, %s)
        """
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, (session_id, "user", user_input))
                cur.execute(sql, (session_id, "assistant", assistant_output))
            conn.commit()

    def close(self) -> None:
        self._pool.close()


class RedisContextStore:
    def __init__(self, redis_url: str, ttl_seconds: int = 1800) -> None:
        self._client = Redis.from_url(redis_url, decode_responses=True)
        self._ttl_seconds = ttl_seconds

    def _key(self, session_id: str) -> str:
        return f"chat:ctx:{session_id}"

    def load_context(self, session_id: str) -> list[dict[str, str]]:
        raw = self._client.get(self._key(session_id))
        if not raw:
            return []
        try:
            data = json.loads(raw)
        except Exception:
            return []
        return data if isinstance(data, list) else []

    def save_context(self, session_id: str, messages: list[dict[str, str]]) -> None:
        self._client.set(
            self._key(session_id),
            json.dumps(messages, ensure_ascii=False),
            ex=self._ttl_seconds,
        )


class HybridMemoryStore:
    def __init__(
        self,
        pg_store: PostgresMemoryStore,
        redis_store: RedisContextStore,
        max_history_messages: int = 12,
    ) -> None:
        self._pg = pg_store
        self._redis = redis_store
        self._max_history_messages = max_history_messages

    def load_context(self, session_id: str) -> list[dict[str, str]]:
        cached = self._redis.load_context(session_id)
        if cached:
            return cached[-self._max_history_messages :]

        history = self._pg.load_context(session_id)
        if history:
            self._redis.save_context(session_id, history[-self._max_history_messages :])
        return history[-self._max_history_messages :]

    def append_turn(self, session_id: str, user_input: str, assistant_output: str) -> None:
        self._pg.append_turn(session_id, user_input, assistant_output)

        current = self._redis.load_context(session_id)
        updated = current + [
            {"role": "user", "content": user_input},
            {"role": "assistant", "content": assistant_output},
        ]
        self._redis.save_context(session_id, updated[-self._max_history_messages :])
