# Backend - StudyMate Agent API

## 功能范围（瘦身版）
- `GET /health` 健康检查
- `POST /chat/agent` 单轮 Agent 对话
- `POST /chat/agent/session` 带会话记忆的 Agent 对话
- `POST /chat/agent/session/stream` 带会话记忆的流式对话（NDJSON）

## 目录结构
```txt
backend/
├─ app/
│  ├─ main.py
│  ├─ core/
│  │  ├─ config.py
│  │  └─ logging.py
│  ├─ routers/
│  │  ├─ system.py
│  │  └─ chat.py
│  ├─ services/
│  │  ├─ agent_service.py
│  │  ├─ chat_service.py
│  │  └─ memory_store.py
│  ├─ tools/
│  │  ├─ calculator.py
│  │  ├─ langchain_tools.py
│  │  └─ search_web.py
│  ├─ schemas/
│  │  └─ api_response.py
│  └─ tests/
│     └─ test_api.py
├─ init_chat_memory.sql
└─ pytest.ini
```

## 运行方式
```bash
# 项目根目录执行
pip install fastapi "uvicorn[standard]" openai python-dotenv \
  langchain langchain-openai langgraph tavily-python psycopg[binary] psycopg-pool redis

uvicorn app.main:app --reload --app-dir backend --port 8000
```

## 本地验证
```bash
# 语法检查
python -m compileall -q backend/app

# 若已安装 pytest
cd backend
python -m pytest -q
```

## 环境变量
请参考项目根目录 `.env.example`。

## 会话记忆策略
优先级：`Postgres + Redis` -> `Postgres` -> `InMemory`。
