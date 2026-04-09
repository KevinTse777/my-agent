from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from functools import lru_cache

from fastapi import HTTPException, status

from app.core.config import settings

logger = logging.getLogger("app.auth_security")


def _utc_now_ts() -> int:
    return int(time.time())


@dataclass(frozen=True)
class LoginLockState:
    locked: bool
    retry_after_seconds: int


class InMemoryLoginAttemptStore:
    def __init__(self) -> None:
        self._failures: dict[str, tuple[int, int]] = {}
        self._locks: dict[str, int] = {}

    def get_lock_state(self, email_key: str, now_ts: int) -> LoginLockState:
        locked_until = self._locks.get(email_key, 0)
        if locked_until <= now_ts:
            self._locks.pop(email_key, None)
            return LoginLockState(locked=False, retry_after_seconds=0)
        return LoginLockState(locked=True, retry_after_seconds=max(1, locked_until - now_ts))

    def record_failed_attempt(self, email_key: str, now_ts: int) -> LoginLockState:
        window_seconds = max(1, settings.auth_login_attempt_window_seconds)
        lock_seconds = max(1, settings.auth_login_lock_seconds)
        max_attempts = max(1, settings.auth_login_max_failed_attempts)

        count, window_started_at = self._failures.get(email_key, (0, now_ts))
        if now_ts - window_started_at >= window_seconds:
            count = 0
            window_started_at = now_ts

        count += 1
        self._failures[email_key] = (count, window_started_at)

        if count >= max_attempts:
            locked_until = now_ts + lock_seconds
            self._locks[email_key] = locked_until
            self._failures.pop(email_key, None)
            return LoginLockState(locked=True, retry_after_seconds=lock_seconds)

        return LoginLockState(locked=False, retry_after_seconds=0)

    def reset_failed_attempts(self, email_key: str) -> None:
        self._failures.pop(email_key, None)
        self._locks.pop(email_key, None)


class RedisLoginAttemptStore:
    def __init__(self, redis_url: str) -> None:
        from redis import Redis

        self._client = Redis.from_url(redis_url, socket_timeout=1, socket_connect_timeout=1, decode_responses=True)

    def _lock_key(self, email_key: str) -> str:
        return f"auth_login_lock:{email_key}"

    def _count_key(self, email_key: str) -> str:
        return f"auth_login_fail_count:{email_key}"

    def get_lock_state(self, email_key: str, now_ts: int) -> LoginLockState:
        ttl = self._client.ttl(self._lock_key(email_key))
        if ttl is None or ttl < 0:
            return LoginLockState(locked=False, retry_after_seconds=0)
        return LoginLockState(locked=True, retry_after_seconds=max(1, int(ttl)))

    def record_failed_attempt(self, email_key: str, now_ts: int) -> LoginLockState:
        count_key = self._count_key(email_key)
        max_attempts = max(1, settings.auth_login_max_failed_attempts)
        window_seconds = max(1, settings.auth_login_attempt_window_seconds)
        lock_seconds = max(1, settings.auth_login_lock_seconds)

        count = self._client.incr(count_key)
        if count == 1:
            self._client.expire(count_key, window_seconds)

        if int(count) >= max_attempts:
            self._client.set(self._lock_key(email_key), "1", ex=lock_seconds)
            self._client.delete(count_key)
            return LoginLockState(locked=True, retry_after_seconds=lock_seconds)

        return LoginLockState(locked=False, retry_after_seconds=0)

    def reset_failed_attempts(self, email_key: str) -> None:
        self._client.delete(self._count_key(email_key), self._lock_key(email_key))


class AuthLoginSecurityService:
    def __init__(self) -> None:
        self._store = self._build_store()

    def _build_store(self):
        if not settings.redis_url:
            logger.info("auth_login_security=inmemory")
            return InMemoryLoginAttemptStore()

        try:
            store = RedisLoginAttemptStore(settings.redis_url)
            logger.info("auth_login_security=redis")
            return store
        except Exception as exc:
            logger.warning("auth_login_security=redis_fallback_inmemory error=%s", str(exc))
            return InMemoryLoginAttemptStore()

    def ensure_login_allowed(self, email_key: str) -> None:
        state = self._store.get_lock_state(email_key=email_key, now_ts=_utc_now_ts())
        if not state.locked:
            return
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many failed login attempts. Try again later.",
            headers={"Retry-After": str(state.retry_after_seconds)},
        )

    def record_failed_login(self, email_key: str) -> None:
        state = self._store.record_failed_attempt(email_key=email_key, now_ts=_utc_now_ts())
        if not state.locked:
            return
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many failed login attempts. Try again later.",
            headers={"Retry-After": str(state.retry_after_seconds)},
        )

    def reset_failed_logins(self, email_key: str) -> None:
        self._store.reset_failed_attempts(email_key)


@lru_cache(maxsize=1)
def get_auth_login_security_service() -> AuthLoginSecurityService:
    return AuthLoginSecurityService()
