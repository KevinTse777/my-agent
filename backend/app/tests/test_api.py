from contextlib import contextmanager
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.core.config import settings, validate_runtime_configuration
from app.main import app
from app.services.auth_store import get_auth_store
from app.services.chat_store import get_chat_store
from app.services.memory_store import PostgresMemoryStore
from app.services.rate_limit_service import get_api_rate_limiter
from app.services.task_broker import ChatTaskJob, KafkaTaskBroker, get_task_broker, inspect_task_broker_runtime
from app.services.task_store import get_task_store
from app.services.task_worker import get_task_worker

client = TestClient(app)


@pytest.fixture(autouse=True)
def reset_stores():
    original_task_broker_backend = settings.task_broker_backend
    original_postgres_url = settings.postgres_url
    original_redis_url = settings.redis_url
    get_chat_store.cache_clear()
    get_auth_store.cache_clear()
    get_task_store.cache_clear()
    get_task_broker.cache_clear()
    get_task_worker.cache_clear()
    get_api_rate_limiter.cache_clear()
    object.__setattr__(settings, "task_broker_backend", "inmemory")
    object.__setattr__(settings, "postgres_url", None)
    object.__setattr__(settings, "redis_url", None)
    yield
    object.__setattr__(settings, "task_broker_backend", original_task_broker_backend)
    object.__setattr__(settings, "postgres_url", original_postgres_url)
    object.__setattr__(settings, "redis_url", original_redis_url)
    get_chat_store.cache_clear()
    get_auth_store.cache_clear()
    get_task_store.cache_clear()
    get_task_broker.cache_clear()
    get_task_worker.cache_clear()
    get_api_rate_limiter.cache_clear()


def register_and_login(email: str | None = None, username: str | None = None, password: str = "password123"):
    unique_suffix = uuid4().hex[:8]
    actual_email = email or f"test_{unique_suffix}@example.com"
    actual_username = username or f"tester_{unique_suffix}"
    client_ip = f"198.51.100.{int(unique_suffix[:2], 16) % 200 + 1}"
    register_resp = client.post(
        "/auth/register",
        json={"email": actual_email, "username": actual_username, "password": password},
        headers={"x-forwarded-for": client_ip},
    )
    assert register_resp.status_code == 200

    login_resp = client.post(
        "/auth/login",
        json={"email": actual_email, "password": password},
        headers={"x-forwarded-for": client_ip},
    )
    assert login_resp.status_code == 200
    return login_resp.json()["data"]


def auth_headers(access_token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {access_token}"}


@contextmanager
def override_runtime_settings(**updates):
    original = {key: getattr(settings, key) for key in updates}
    try:
        for key, value in updates.items():
            object.__setattr__(settings, key, value)
        yield
    finally:
        for key, value in original.items():
            object.__setattr__(settings, key, value)


def test_health():
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_register_login_me_refresh_logout_flow():
    auth = register_and_login()
    me_resp = client.get("/me", headers=auth_headers(auth["access_token"]))
    assert me_resp.status_code == 200
    assert me_resp.json()["data"]["email"] == auth["user"]["email"]

    refresh_resp = client.post("/auth/refresh", json={"refresh_token": auth["refresh_token"]})
    assert refresh_resp.status_code == 200
    refreshed = refresh_resp.json()["data"]
    assert refreshed["token_type"] == "bearer"
    assert refreshed["user"]["username"] == auth["user"]["username"]

    logout_resp = client.post("/auth/logout", json={"refresh_token": refreshed["refresh_token"]})
    assert logout_resp.status_code == 200
    assert logout_resp.json()["data"]["logged_out"] is True


def test_api_rate_limit_blocks_repeated_login_attempts():
    with override_runtime_settings(
        api_rate_limit_enabled=True,
        api_rate_limit_window_seconds=60,
        api_rate_limit_auth_max_requests=2,
        redis_url=None,
    ):
        get_api_rate_limiter.cache_clear()
        password = "password123"
        email = f"login_limit_{uuid4().hex[:8]}@example.com"
        username = f"login_limit_{uuid4().hex[:8]}"
        client_ip = f"203.0.113.{int(uuid4().hex[:2], 16) % 200 + 1}"
        register_resp = client.post(
            "/auth/register",
            json={"email": email, "username": username, "password": password},
            headers={"x-forwarded-for": client_ip},
        )
        assert register_resp.status_code == 200

        first = client.post(
            "/auth/login",
            json={"email": email, "password": "wrong-pass-1"},
            headers={"x-forwarded-for": client_ip},
        )
        second = client.post(
            "/auth/login",
            json={"email": email, "password": "wrong-pass-2"},
            headers={"x-forwarded-for": client_ip},
        )
        third = client.post(
            "/auth/login",
            json={"email": email, "password": password},
            headers={"x-forwarded-for": client_ip},
        )

        assert first.status_code == 401
        assert second.status_code == 401
        assert third.status_code == 429
        assert third.json()["message"] == "Too Many Requests"
        assert third.headers["Retry-After"] == "60"
        assert third.headers["X-RateLimit-Limit"] == "2"
        assert third.headers["X-RateLimit-Remaining"] == "0"


def test_api_rate_limit_blocks_repeated_public_chat_requests(monkeypatch):
    with override_runtime_settings(
        api_rate_limit_enabled=True,
        api_rate_limit_window_seconds=60,
        api_rate_limit_chat_max_requests=1,
        redis_url=None,
    ):
        get_api_rate_limiter.cache_clear()
        client_ip = f"203.0.113.{int(uuid4().hex[:2], 16) % 200 + 1}"

        def fake_agent_chat(message: str):
            return {
                "answer": f"ok:{message}",
                "tools_used": [],
                "agent_duration_ms": 1.23,
                "sources": [],
            }

        monkeypatch.setattr("app.routers.chat.agent_chat", fake_agent_chat)

        first = client.post(
            "/chat/agent",
            json={"message": "第一次请求"},
            headers={"x-forwarded-for": client_ip},
        )
        second = client.post(
            "/chat/agent",
            json={"message": "第二次请求"},
            headers={"x-forwarded-for": client_ip},
        )

        assert first.status_code == 200
        assert second.status_code == 429
        assert second.json()["message"] == "Too Many Requests"


def test_api_rate_limit_does_not_apply_to_health_endpoint():
    with override_runtime_settings(
        api_rate_limit_enabled=True,
        api_rate_limit_window_seconds=60,
        api_rate_limit_auth_max_requests=1,
        api_rate_limit_chat_max_requests=1,
        api_rate_limit_task_create_max_requests=1,
        redis_url=None,
    ):
        get_api_rate_limiter.cache_clear()
        client_ip = f"203.0.113.{int(uuid4().hex[:2], 16) % 200 + 1}"
        first = client.get("/health", headers={"x-forwarded-for": client_ip})
        second = client.get("/health", headers={"x-forwarded-for": client_ip})
        third = client.get("/health", headers={"x-forwarded-for": client_ip})

        assert first.status_code == 200
        assert second.status_code == 200
        assert third.status_code == 200


def test_business_routes_require_auth():
    resp = client.get("/chat/sessions")
    assert resp.status_code == 401

    resp = client.post(
        "/chat/agent/session",
        json={"session_id": "sess_private_001", "message": "你好"},
    )
    assert resp.status_code == 401


def test_agent_endpoint_shape():
    resp = client.post("/chat/agent", json={"message": "请计算 2+3"})
    assert resp.status_code in (200, 400, 500)
    body = resp.json()
    if resp.status_code == 200:
        payload = body.get("data", body)
        assert "answer" in payload


def test_agent_endpoint_mocked(monkeypatch):
    def fake_agent_chat(message: str):
        return {
            "answer": f"mocked answer for: {message}",
            "tools_used": ["calculator_tool"],
            "agent_duration_ms": 12.34,
            "sources": [],
        }

    monkeypatch.setattr("app.routers.chat.agent_chat", fake_agent_chat)
    resp = client.post("/chat/agent", json={"message": "请计算 2+3"})
    assert resp.status_code == 200
    payload = resp.json()["data"]
    assert payload["answer"].startswith("mocked answer")
    assert payload["tools_used"] == ["calculator_tool"]


def test_chat_sessions_crud_with_auth():
    auth = register_and_login()

    create_resp = client.post(
        "/chat/sessions",
        json={"title": "测试会话"},
        headers=auth_headers(auth["access_token"]),
    )
    assert create_resp.status_code == 200
    session = create_resp.json()["data"]
    session_id = session["id"]
    assert session["title"] == "测试会话"
    assert session["user_id"] == auth["user"]["id"]

    list_resp = client.get("/chat/sessions", headers=auth_headers(auth["access_token"]))
    assert list_resp.status_code == 200
    sessions = list_resp.json()["data"]["sessions"]
    assert any(item["id"] == session_id for item in sessions)

    delete_resp = client.delete(
        f"/chat/sessions/{session_id}",
        headers=auth_headers(auth["access_token"]),
    )
    assert delete_resp.status_code == 200

    missing_resp = client.get(
        f"/chat/sessions/{session_id}/messages",
        headers=auth_headers(auth["access_token"]),
    )
    assert missing_resp.status_code == 404


def test_agent_session_persists_business_messages_for_current_user(monkeypatch):
    auth = register_and_login()

    def fake_agent_session_chat(message: str, session_id: str):
        return {
            "session_id": session_id,
            "answer": f"已收到：{message}",
            "tools_used": ["calculator_tool"],
            "sources": [{"title": "示例来源", "url": "https://example.com"}],
        }

    monkeypatch.setattr("app.services.chat_service.run_agent_with_session", fake_agent_session_chat)

    resp = client.post(
        "/chat/agent/session",
        json={"session_id": "sess_business_001", "message": "帮我整理这段内容"},
        headers=auth_headers(auth["access_token"]),
    )
    assert resp.status_code == 200

    messages_resp = client.get(
        "/chat/sessions/sess_business_001/messages",
        headers=auth_headers(auth["access_token"]),
    )
    assert messages_resp.status_code == 200
    messages = messages_resp.json()["data"]["messages"]

    assert len(messages) == 2
    assert messages[0]["role"] == "user"
    assert messages[1]["role"] == "assistant"
    assert messages[1]["tools_used"] == ["calculator_tool"]
    assert messages[1]["sources"][0]["url"] == "https://example.com"


def test_chat_session_access_isolated_between_users(monkeypatch):
    first = register_and_login("user1@example.com", "user1", "password123")
    second = register_and_login("user2@example.com", "user2", "password123")

    def fake_agent_session_chat(message: str, session_id: str):
        return {"session_id": session_id, "answer": f"ok:{message}", "tools_used": [], "sources": []}

    monkeypatch.setattr("app.services.chat_service.run_agent_with_session", fake_agent_session_chat)

    resp = client.post(
        "/chat/agent/session",
        json={"session_id": "sess_isolated_001", "message": "第一位用户的内容"},
        headers=auth_headers(first["access_token"]),
    )
    assert resp.status_code == 200

    forbidden = client.get(
        "/chat/sessions/sess_isolated_001/messages",
        headers=auth_headers(second["access_token"]),
    )
    assert forbidden.status_code == 403


def test_agent_session_stream_endpoint_mocked(monkeypatch):
    auth = register_and_login()

    async def fake_stream(user_id: str, session_id: str, message: str):
        assert user_id == auth["user"]["id"]
        yield {"type": "token", "content": "你好"}
        yield {
            "type": "end",
            "session_id": session_id,
            "answer": f"mocked stream answer for: {message}",
            "tools_used": ["calculator_tool"],
            "sources": [],
            "agent_duration_ms": 10.0,
        }

    monkeypatch.setattr("app.routers.chat.agent_session_chat_stream", fake_stream)

    resp = client.post(
        "/chat/agent/session/stream",
        json={"session_id": "sess_test_stream_001", "message": "流式测试"},
        headers=auth_headers(auth["access_token"]),
    )
    assert resp.status_code == 200
    lines = [line for line in resp.text.splitlines() if line.strip()]
    assert len(lines) >= 2
    assert '"type": "start"' in lines[0]
    assert any('"type": "token"' in line for line in lines)
    assert any('"type": "end"' in line for line in lines)


def test_chat_task_lifecycle_success(monkeypatch):
    auth = register_and_login()

    processed_jobs: list[ChatTaskJob] = []

    def fake_enqueue(job: ChatTaskJob):
        processed_jobs.append(job)
        get_task_worker().process_job(job)

    def fake_run_agent_with_session(message: str, session_id: str):
        return {
            "session_id": session_id,
            "answer": f"异步结果：{message}",
            "tools_used": ["calculator_tool"],
            "sources": [{"title": "async", "url": "https://example.com/async"}],
        }

    monkeypatch.setattr(get_task_broker(), "publish_chat_task", fake_enqueue)
    monkeypatch.setattr("app.services.chat_service.run_agent_with_session", fake_run_agent_with_session)

    create_resp = client.post(
        "/chat/tasks",
        json={"session_id": "sess_task_001", "message": "帮我异步处理这段文本"},
        headers=auth_headers(auth["access_token"]),
    )
    assert create_resp.status_code == 200
    task = create_resp.json()["data"]
    assert task["status"] == "queued"
    assert processed_jobs

    status_resp = client.get(
        f"/chat/tasks/{task['id']}",
        headers=auth_headers(auth["access_token"]),
    )
    assert status_resp.status_code == 200
    status_data = status_resp.json()["data"]
    assert status_data["status"] == "succeeded"
    assert status_data["result"]["answer"] == "异步结果：帮我异步处理这段文本"

    result_resp = client.get(
        f"/chat/tasks/{task['id']}/result",
        headers=auth_headers(auth["access_token"]),
    )
    assert result_resp.status_code == 200
    result_data = result_resp.json()["data"]
    assert result_data["status"] == "succeeded"
    assert result_data["result"]["tools_used"] == ["calculator_tool"]

    messages_resp = client.get(
        "/chat/sessions/sess_task_001/messages",
        headers=auth_headers(auth["access_token"]),
    )
    assert messages_resp.status_code == 200
    messages = messages_resp.json()["data"]["messages"]
    assert len(messages) == 2
    assert messages[1]["content"] == "异步结果：帮我异步处理这段文本"


def test_chat_task_result_not_ready(monkeypatch):
    auth = register_and_login()

    captured_jobs: list[ChatTaskJob] = []

    def fake_enqueue(job: ChatTaskJob):
        captured_jobs.append(job)

    monkeypatch.setattr(get_task_broker(), "publish_chat_task", fake_enqueue)

    create_resp = client.post(
        "/chat/tasks",
        json={"session_id": "sess_task_pending_001", "message": "稍后处理"},
        headers=auth_headers(auth["access_token"]),
    )
    assert create_resp.status_code == 200
    task_id = create_resp.json()["data"]["id"]
    assert captured_jobs

    result_resp = client.get(
        f"/chat/tasks/{task_id}/result",
        headers=auth_headers(auth["access_token"]),
    )
    assert result_resp.status_code == 409


def test_chat_task_access_isolated_between_users(monkeypatch):
    first = register_and_login("task1@example.com", "task1", "password123")
    second = register_and_login("task2@example.com", "task2", "password123")

    def fake_enqueue(job: ChatTaskJob):
        get_task_worker().process_job(job)

    def fake_run_agent_with_session(message: str, session_id: str):
        return {"session_id": session_id, "answer": "ok", "tools_used": [], "sources": []}

    monkeypatch.setattr(get_task_broker(), "publish_chat_task", fake_enqueue)
    monkeypatch.setattr("app.services.chat_service.run_agent_with_session", fake_run_agent_with_session)

    create_resp = client.post(
        "/chat/tasks",
        json={"session_id": "sess_task_private_001", "message": "只属于第一个用户"},
        headers=auth_headers(first["access_token"]),
    )
    assert create_resp.status_code == 200
    task_id = create_resp.json()["data"]["id"]

    forbidden = client.get(
        f"/chat/tasks/{task_id}",
        headers=auth_headers(second["access_token"]),
    )
    assert forbidden.status_code == 404


def test_kafka_mode_requires_postgres_for_shared_storage():
    with override_runtime_settings(
        task_broker_backend="kafka",
        kafka_bootstrap_servers="127.0.0.1:9092",
        postgres_url=None,
    ):
        get_auth_store.cache_clear()
        get_chat_store.cache_clear()
        get_task_store.cache_clear()

        with pytest.raises(RuntimeError, match="POSTGRES_URL is required"):
            validate_runtime_configuration()
        with pytest.raises(RuntimeError, match="POSTGRES_URL is required"):
            get_task_store()
        with pytest.raises(RuntimeError, match="POSTGRES_URL is required"):
            get_chat_store()
        with pytest.raises(RuntimeError, match="POSTGRES_URL is required"):
            get_auth_store()


def test_kafka_mode_requires_kafka_python_dependency(monkeypatch):
    with override_runtime_settings(
        task_broker_backend="kafka",
        kafka_bootstrap_servers="127.0.0.1:9092",
        postgres_url="postgresql://demo:demo@localhost:5432/demo",
    ):
        monkeypatch.setattr("app.core.config.find_spec", lambda name: None if name == "kafka" else object())

        with pytest.raises(RuntimeError, match="kafka-python is required"):
            validate_runtime_configuration()


def test_task_worker_skips_non_queued_task(monkeypatch):
    with override_runtime_settings(task_broker_backend="inmemory"):
        get_auth_store.cache_clear()
        get_chat_store.cache_clear()
        get_task_store.cache_clear()
        get_task_worker.cache_clear()

        auth = register_and_login()
        task = get_task_store().create_chat_task(
            user_id=auth["user"]["id"],
            session_id="sess_skip_001",
            input_text="skip me",
            request_id="req_skip_001",
        )
        get_task_store().mark_chat_task_succeeded(task["id"], {"answer": "done"})

        def should_not_run(*args, **kwargs):
            raise AssertionError("agent_session_chat should not run for non-queued tasks")

        monkeypatch.setattr("app.services.chat_service.run_agent_with_session", should_not_run)

        get_task_worker().process_job(
            ChatTaskJob(
                task_id=task["id"],
                user_id=auth["user"]["id"],
                session_id="sess_skip_001",
                message="skip me",
                request_id="req_skip_001",
            )
        )

        latest = get_task_store().get_chat_task(user_id=auth["user"]["id"], task_id=task["id"])
        assert latest is not None
        assert latest["status"] == "succeeded"
        assert latest["result"]["answer"] == "done"


def test_inspect_task_broker_runtime_inmemory():
    with override_runtime_settings(task_broker_backend="inmemory"):
        get_task_broker.cache_clear()
        runtime = inspect_task_broker_runtime()
        assert runtime["broker_backend"] == "inmemory"
        assert runtime["consumer_mode"] == "embedded_worker"


def test_inspect_task_broker_runtime_kafka_fallback(monkeypatch):
    with override_runtime_settings(
        task_broker_backend="kafka",
        kafka_bootstrap_servers="127.0.0.1:9092",
        postgres_url="postgresql://demo:demo@localhost:5432/demo",
    ):
        get_task_broker.cache_clear()
        monkeypatch.setattr(KafkaTaskBroker, "_consumer_group_ready", lambda self: False)

        runtime = inspect_task_broker_runtime()
        assert runtime["broker_backend"] == "kafka"
        assert runtime["consumer_mode"] == "direct_partition_fallback"
        assert runtime["consumer_group"] == settings.kafka_chat_task_consumer_group


def test_inspect_task_broker_runtime_detailed(monkeypatch):
    with override_runtime_settings(
        task_broker_backend="kafka",
        kafka_bootstrap_servers="127.0.0.1:9092",
        postgres_url="postgresql://demo:demo@localhost:5432/demo",
    ):
        get_task_broker.cache_clear()
        monkeypatch.setattr(KafkaTaskBroker, "_consumer_group_ready", lambda self: False)

        class FakeConsumer:
            def __init__(self, *args, **kwargs):
                pass

            def bootstrap_connected(self):
                return True

            def partitions_for_topic(self, topic):
                assert topic == settings.kafka_chat_task_topic
                return {0}

            def topics(self, exclude_internal_topics=True):
                assert exclude_internal_topics is False
                return {settings.kafka_chat_task_topic, "__consumer_offsets"}

            def close(self):
                return None

        def fake_load_kafka(self):
            return object, FakeConsumer, object, object

        monkeypatch.setattr(KafkaTaskBroker, "_load_kafka", fake_load_kafka)

        from app.services.task_broker import inspect_task_broker_runtime_detailed

        runtime = inspect_task_broker_runtime_detailed()
        assert runtime["broker_backend"] == "kafka"
        assert runtime["consumer_mode"] == "direct_partition_fallback"
        assert runtime["bootstrap_connected"] == "yes"
        assert runtime["topic_exists"] == "yes"
        assert runtime["topic_partitions"] == "0"
        assert runtime["consumer_offsets_topic_visible"] == "yes"


def test_inspect_task_broker_runtime_detailed_legacy_topics_api(monkeypatch):
    with override_runtime_settings(
        task_broker_backend="kafka",
        kafka_bootstrap_servers="127.0.0.1:9092",
        postgres_url="postgresql://demo:demo@localhost:5432/demo",
    ):
        get_task_broker.cache_clear()
        monkeypatch.setattr(KafkaTaskBroker, "_consumer_group_ready", lambda self: True)

        class FakeConsumer:
            def __init__(self, *args, **kwargs):
                pass

            def bootstrap_connected(self):
                return True

            def partitions_for_topic(self, topic):
                assert topic == settings.kafka_chat_task_topic
                return {0}

            def topics(self, *args, **kwargs):
                if kwargs:
                    raise TypeError("KafkaConsumer.topics() got an unexpected keyword argument 'exclude_internal_topics'")
                return {settings.kafka_chat_task_topic}

            def close(self):
                return None

        def fake_load_kafka(self):
            return object, FakeConsumer, object, object

        monkeypatch.setattr(KafkaTaskBroker, "_load_kafka", fake_load_kafka)

        from app.services.task_broker import inspect_task_broker_runtime_detailed

        runtime = inspect_task_broker_runtime_detailed()
        assert runtime["broker_backend"] == "kafka"
        assert runtime["consumer_mode"] == "consumer_group"
        assert runtime["bootstrap_connected"] == "yes"
        assert runtime["topic_exists"] == "yes"
        assert runtime["consumer_offsets_topic_visible"] == "unknown"
        assert "consumer_offsets_note" in runtime


def test_postgres_memory_store_ensures_schema(monkeypatch):
    executed_sql: list[str] = []

    class FakeCursor:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def execute(self, sql, params=None):
            executed_sql.append(" ".join(sql.split()))

    class FakeConnection:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def cursor(self):
            return FakeCursor()

        def commit(self):
            executed_sql.append("COMMIT")

    class FakeConnectionContext:
        def __enter__(self):
            return FakeConnection()

        def __exit__(self, exc_type, exc, tb):
            return False

    class FakePool:
        def __init__(self, *args, **kwargs):
            pass

        def connection(self):
            return FakeConnectionContext()

    monkeypatch.setattr("app.services.memory_store.ConnectionPool", FakePool)

    PostgresMemoryStore("postgresql://demo:demo@localhost:5432/demo")

    assert any("CREATE TABLE IF NOT EXISTS chat_messages" in sql for sql in executed_sql)
    assert any("CREATE INDEX IF NOT EXISTS idx_chat_messages_session_created_at" in sql for sql in executed_sql)
    assert "COMMIT" in executed_sql


def test_task_worker_requeues_failed_task_before_final_failure(monkeypatch):
    with override_runtime_settings(task_broker_backend="inmemory", task_worker_max_retries=1):
        get_auth_store.cache_clear()
        get_chat_store.cache_clear()
        get_task_store.cache_clear()
        get_task_worker.cache_clear()
        get_task_broker.cache_clear()

        auth = register_and_login()
        task = get_task_store().create_chat_task(
            user_id=auth["user"]["id"],
            session_id="sess_retry_001",
            input_text="retry me",
            request_id="req_retry_001",
        )

        published_jobs: list[ChatTaskJob] = []
        dlq_events: list[tuple[str, int]] = []

        monkeypatch.setattr(get_task_broker(), "publish_chat_task", lambda job: published_jobs.append(job))
        monkeypatch.setattr(
            get_task_broker(),
            "publish_chat_task_dlq",
            lambda job, error_message, retry_count: dlq_events.append((error_message, retry_count)),
        )
        monkeypatch.setattr("app.services.chat_service.run_agent_with_session", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("boom")))

        get_task_worker().process_job(
            ChatTaskJob(
                task_id=task["id"],
                user_id=auth["user"]["id"],
                session_id="sess_retry_001",
                message="retry me",
                request_id="req_retry_001",
            )
        )

        latest = get_task_store().get_chat_task(user_id=auth["user"]["id"], task_id=task["id"])
        assert latest is not None
        assert latest["status"] == "queued"
        assert latest["retry_count"] == 1
        assert len(published_jobs) == 1
        assert dlq_events == []


def test_task_worker_publishes_dlq_after_retry_exhausted(monkeypatch):
    with override_runtime_settings(task_broker_backend="inmemory", task_worker_max_retries=1):
        get_auth_store.cache_clear()
        get_chat_store.cache_clear()
        get_task_store.cache_clear()
        get_task_worker.cache_clear()
        get_task_broker.cache_clear()

        auth = register_and_login()
        session_id = f"sess_dlq_{uuid4().hex[:8]}"
        get_chat_store().create_session(user_id=auth["user"]["id"], session_id=session_id)
        task = get_task_store().create_chat_task(
            user_id=auth["user"]["id"],
            session_id=session_id,
            input_text="fail me",
            request_id="req_dlq_001",
        )
        get_task_store().requeue_chat_task(task["id"], "first failure")

        published_jobs: list[ChatTaskJob] = []
        dlq_events: list[tuple[str, int]] = []

        monkeypatch.setattr(get_task_broker(), "publish_chat_task", lambda job: published_jobs.append(job))
        monkeypatch.setattr(
            get_task_broker(),
            "publish_chat_task_dlq",
            lambda job, error_message, retry_count: dlq_events.append((error_message, retry_count)),
        )
        monkeypatch.setattr("app.services.chat_service.run_agent_with_session", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("still boom")))

        get_task_worker().process_job(
            ChatTaskJob(
                task_id=task["id"],
                user_id=auth["user"]["id"],
                session_id=session_id,
                message="fail me",
                request_id="req_dlq_001",
            )
        )

        latest = get_task_store().get_chat_task(user_id=auth["user"]["id"], task_id=task["id"])
        assert latest is not None
        assert latest["status"] == "failed"
        assert latest["retry_count"] == 2
        assert published_jobs == []
        assert dlq_events == [("still boom", 2)]
