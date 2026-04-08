import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.auth_store import get_auth_store
from app.services.chat_store import get_chat_store
from app.services.task_broker import ChatTaskJob, get_task_broker
from app.services.task_store import get_task_store
from app.services.task_worker import get_task_worker

client = TestClient(app)


@pytest.fixture(autouse=True)
def reset_stores():
    get_chat_store.cache_clear()
    get_auth_store.cache_clear()
    get_task_store.cache_clear()
    get_task_broker.cache_clear()
    get_task_worker.cache_clear()
    yield
    get_chat_store.cache_clear()
    get_auth_store.cache_clear()
    get_task_store.cache_clear()
    get_task_broker.cache_clear()
    get_task_worker.cache_clear()


def register_and_login(email: str = "test@example.com", username: str = "tester", password: str = "password123"):
    register_resp = client.post(
        "/auth/register",
        json={"email": email, "username": username, "password": password},
    )
    assert register_resp.status_code == 200

    login_resp = client.post("/auth/login", json={"email": email, "password": password})
    assert login_resp.status_code == 200
    return login_resp.json()["data"]


def auth_headers(access_token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {access_token}"}


def test_health():
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_register_login_me_refresh_logout_flow():
    auth = register_and_login()
    me_resp = client.get("/me", headers=auth_headers(auth["access_token"]))
    assert me_resp.status_code == 200
    assert me_resp.json()["data"]["email"] == "test@example.com"

    refresh_resp = client.post("/auth/refresh", json={"refresh_token": auth["refresh_token"]})
    assert refresh_resp.status_code == 200
    refreshed = refresh_resp.json()["data"]
    assert refreshed["token_type"] == "bearer"
    assert refreshed["user"]["username"] == "tester"

    logout_resp = client.post("/auth/logout", json={"refresh_token": refreshed["refresh_token"]})
    assert logout_resp.status_code == 200
    assert logout_resp.json()["data"]["logged_out"] is True


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
