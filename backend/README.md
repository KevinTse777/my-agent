# Backend - StudyMate Agent API

## 功能范围（瘦身版）
- `GET /health` 健康检查
- `POST /auth/register` 注册
- `POST /auth/login` 登录
- `POST /auth/refresh` 刷新 token
- `POST /auth/logout` 退出登录
- `GET /me` 获取当前用户
- `GET /chat/sessions` 业务会话列表
- `POST /chat/sessions` 创建业务会话
- `GET /chat/sessions/{id}/messages` 查询业务消息历史
- `DELETE /chat/sessions/{id}` 删除业务会话
- `POST /chat/tasks` 创建异步聊天任务
- `GET /chat/tasks/{task_id}` 查询任务状态
- `GET /chat/tasks/{task_id}/result` 查询任务结果
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
│  ├─ dependencies/
│  │  └─ auth.py
│  ├─ routers/
│  │  ├─ auth.py
│  │  ├─ system.py
│  │  └─ chat.py
│  ├─ services/
│  │  ├─ agent_service.py
│  │  ├─ auth_service.py
│  │  ├─ auth_store.py
│  │  ├─ chat_service.py
│  │  ├─ chat_store.py
│  │  ├─ memory_store.py
│  │  ├─ task_broker.py
│  │  ├─ task_store.py
│  │  └─ task_worker.py
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

# 独立 worker（Kafka 模式）
python backend/scripts/run_task_worker.py
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

## 业务会话存储策略
- 业务会话与 Agent 记忆分层存储，避免混用
- 优先使用 `POSTGRES_URL` 自动建表存储
- 未配置 Postgres 时回退为进程内 `InMemory`

## 用户与鉴权策略
- 注册与登录使用业务层 `app_users` / `app_user_sessions`
- Access Token 与 Refresh Token 使用 `Bearer` 方式传递
- 业务会话接口和带会话聊天接口需要登录后访问
- `POST /chat/agent` 保留为开发调试用单轮入口

## 异步聊天任务策略
- 当前已支持“提交任务 + 轮询结果”模式
- API 负责创建 `chat task` 并投递到 `task broker`
- Worker 负责消费任务并执行带会话聊天链路，随后写回业务会话与任务结果
- 默认 broker 为进程内 `InMemory` 队列，便于本地直接运行
- 切换 `TASK_BROKER_BACKEND=kafka` 后，API 不再启动内置 worker，需要单独运行 `backend/scripts/run_task_worker.py`
- Kafka 模式依赖额外安装 `kafka-python`
