from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health():
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_calculate_ok():
    resp = client.post("/tools/calculate", json={"expression": "(2+3)*4"})
    assert resp.status_code == 200
    data = resp.json()
    # 兼容你当前是否使用 ApiResponse 包裹
    payload = data.get("data", data)
    assert payload["result"] == 20.0


def test_agent_endpoint_shape():
    resp = client.post("/chat/agent", json={"message": "请计算 2+3"})
    assert resp.status_code in (200, 400, 500)  # 先保证接口可达
    body = resp.json()

    # 成功时验证结构
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

    # chat.py 在模块导入时已绑定了 agent_chat，需 patch 路由模块命名空间
    monkeypatch.setattr("app.routers.chat.agent_chat", fake_agent_chat)

    resp = client.post("/chat/agent", json={"message": "请计算 2+3"})
    assert resp.status_code == 200

    body = resp.json()
    payload = body.get("data", body)

    assert payload["answer"].startswith("mocked answer")
    assert payload["tools_used"] == ["calculator_tool"]

def test_chain_endpoint_mocked(monkeypatch):
    def fake_chain_chat(message: str):
        return {"answer": f"mock chain: {message}"}

    monkeypatch.setattr("app.routers.chat.chain_chat", fake_chain_chat)

    resp = client.post("/chat/chain", json={"message": "解释 chain"})
    assert resp.status_code == 200

    body = resp.json()
    payload = body.get("data", body)
    assert payload["answer"].startswith("mock chain:")


def test_auto_tool_endpoint_mocked(monkeypatch):
    def fake_auto_tool(message: str):
        return {
            "answer": f"mock auto tool: {message}",
            "tools_used": ["calculator"],
        }

    monkeypatch.setattr("app.routers.chat.chat_with_auto_tool", fake_auto_tool)

    resp = client.post("/chat/auto-tool", json={"message": "请计算 2+3"})
    assert resp.status_code == 200

    body = resp.json()
    payload = body.get("data", body)
    assert payload["answer"].startswith("mock auto tool:")
    assert "tools_used" in payload
