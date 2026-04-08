from __future__ import annotations

import logging
import math
import threading
import time
from collections import deque
from dataclasses import dataclass
from functools import lru_cache

from fastapi import Request

from app.core.config import settings

logger = logging.getLogger("app.rate_limit")


@dataclass(frozen=True)
class RateLimitRule:
    name: str
    max_requests: int
    window_seconds: int


@dataclass(frozen=True)
class RateLimitDecision:
    limited: bool
    limit: int
    remaining: int
    retry_after_seconds: int
    rule_name: str
    client_key: str


class InMemoryRateLimiter:
    def __init__(self) -> None:
        self._buckets: dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    def check(self, bucket_key: str, rule: RateLimitRule, now: float | None = None) -> RateLimitDecision:
        current_time = now if now is not None else time.time()
        window_start = current_time - rule.window_seconds

        with self._lock:
            bucket = self._buckets.setdefault(bucket_key, deque())
            while bucket and bucket[0] <= window_start:
                bucket.popleft()

            if len(bucket) >= rule.max_requests:
                retry_after_seconds = max(1, math.ceil(bucket[0] + rule.window_seconds - current_time))
                return RateLimitDecision(
                    limited=True,
                    limit=rule.max_requests,
                    remaining=0,
                    retry_after_seconds=retry_after_seconds,
                    rule_name=rule.name,
                    client_key=bucket_key,
                )

            bucket.append(current_time)
            remaining = max(0, rule.max_requests - len(bucket))
            return RateLimitDecision(
                limited=False,
                limit=rule.max_requests,
                remaining=remaining,
                retry_after_seconds=0,
                rule_name=rule.name,
                client_key=bucket_key,
            )


class RedisRateLimiter:
    def __init__(self, redis_url: str) -> None:
        from redis import Redis

        self._client = Redis.from_url(redis_url, socket_timeout=1, socket_connect_timeout=1, decode_responses=True)

    def check(self, bucket_key: str, rule: RateLimitRule, now: float | None = None) -> RateLimitDecision:
        current_time = now if now is not None else time.time()
        window_slot = int(current_time // rule.window_seconds)
        redis_key = f"rate_limit:{bucket_key}:{window_slot}"

        pipeline = self._client.pipeline()
        pipeline.incr(redis_key)
        pipeline.ttl(redis_key)
        count, ttl = pipeline.execute()

        if count == 1:
            ttl = rule.window_seconds
            self._client.expire(redis_key, rule.window_seconds)
        elif ttl is None or ttl < 0:
            ttl = rule.window_seconds
            self._client.expire(redis_key, rule.window_seconds)

        if count > rule.max_requests:
            return RateLimitDecision(
                limited=True,
                limit=rule.max_requests,
                remaining=0,
                retry_after_seconds=max(1, int(ttl)),
                rule_name=rule.name,
                client_key=bucket_key,
            )

        return RateLimitDecision(
            limited=False,
            limit=rule.max_requests,
            remaining=max(0, rule.max_requests - int(count)),
            retry_after_seconds=0,
            rule_name=rule.name,
            client_key=bucket_key,
        )


class ApiRateLimiter:
    def __init__(self) -> None:
        self._backend = self._build_backend()

    def _build_backend(self):
        if not settings.redis_url:
            logger.info("api_rate_limiter=inmemory")
            return InMemoryRateLimiter()

        try:
            backend = RedisRateLimiter(settings.redis_url)
            logger.info("api_rate_limiter=redis")
            return backend
        except Exception as exc:
            logger.warning("api_rate_limiter=redis_fallback_inmemory error=%s", str(exc))
            return InMemoryRateLimiter()

    def check(self, request: Request) -> RateLimitDecision | None:
        if not settings.api_rate_limit_enabled:
            return None

        rule = _match_rule(request)
        if rule is None:
            return None

        client_key = _resolve_client_key(request)
        bucket_key = f"{rule.name}:{client_key}"
        return self._backend.check(bucket_key, rule)


def _match_rule(request: Request) -> RateLimitRule | None:
    window_seconds = max(1, settings.api_rate_limit_window_seconds)
    rules = {
        ("POST", "/auth/register"): RateLimitRule(
            name="auth_register",
            max_requests=max(1, settings.api_rate_limit_auth_max_requests),
            window_seconds=window_seconds,
        ),
        ("POST", "/auth/login"): RateLimitRule(
            name="auth_login",
            max_requests=max(1, settings.api_rate_limit_auth_max_requests),
            window_seconds=window_seconds,
        ),
        ("POST", "/auth/refresh"): RateLimitRule(
            name="auth_refresh",
            max_requests=max(1, settings.api_rate_limit_auth_max_requests),
            window_seconds=window_seconds,
        ),
        ("POST", "/chat/agent"): RateLimitRule(
            name="chat_agent",
            max_requests=max(1, settings.api_rate_limit_chat_max_requests),
            window_seconds=window_seconds,
        ),
        ("POST", "/chat/agent/session"): RateLimitRule(
            name="chat_agent_session",
            max_requests=max(1, settings.api_rate_limit_chat_max_requests),
            window_seconds=window_seconds,
        ),
        ("POST", "/chat/agent/session/stream"): RateLimitRule(
            name="chat_agent_session_stream",
            max_requests=max(1, settings.api_rate_limit_chat_max_requests),
            window_seconds=window_seconds,
        ),
        ("POST", "/chat/tasks"): RateLimitRule(
            name="chat_tasks_create",
            max_requests=max(1, settings.api_rate_limit_task_create_max_requests),
            window_seconds=window_seconds,
        ),
    }
    return rules.get((request.method.upper(), request.url.path))


def _resolve_client_key(request: Request) -> str:
    forwarded_for = request.headers.get("x-forwarded-for", "").strip()
    if forwarded_for:
        return forwarded_for.split(",")[0].strip() or "unknown"

    if request.client and request.client.host:
        return request.client.host

    return "unknown"


@lru_cache(maxsize=1)
def get_api_rate_limiter() -> ApiRateLimiter:
    return ApiRateLimiter()
