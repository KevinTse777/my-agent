from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health():
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


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

    body = resp.json()
    payload = body.get("data", body)

    assert payload["answer"].startswith("mocked answer")
    assert payload["tools_used"] == ["calculator_tool"]


def test_agent_session_endpoint_mocked(monkeypatch):
    def fake_agent_session_chat(session_id: str, message: str):
        return {
            "session_id": session_id,
            "answer": f"mocked session answer for: {message}",
            "tools_used": ["web_search_tool"],
        }

    monkeypatch.setattr("app.routers.chat.agent_session_chat", fake_agent_session_chat)

    resp = client.post(
        "/chat/agent/session",
        json={"session_id": "sess_test_001", "message": "今天的新闻"},
    )
    assert resp.status_code == 200

    body = resp.json()
    payload = body.get("data", body)

    assert payload["session_id"] == "sess_test_001"
    assert payload["answer"].startswith("mocked session answer")


def test_agent_session_stream_endpoint_mocked(monkeypatch):
    async def fake_stream(session_id: str, message: str):
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
    )
    assert resp.status_code == 200
    lines = [line for line in resp.text.splitlines() if line.strip()]
    assert len(lines) >= 2
    assert '"type": "start"' in lines[0]
    assert any('"type": "token"' in line for line in lines)
    assert any('"type": "end"' in line for line in lines)
