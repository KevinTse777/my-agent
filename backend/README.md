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

# 可选：启动本地 Postgres + Kafka（标准 consumer group 联调基线）
docker compose -f docker-compose.kafka-local.yml up -d

uvicorn app.main:app --reload --app-dir backend --port 8000

# 独立 worker（Kafka 模式）
python backend/scripts/run_task_worker.py --check
python backend/scripts/run_task_worker.py --diagnose
python backend/scripts/run_task_worker.py

# API -> Kafka -> worker -> Postgres 全链路 smoke 验收
python backend/scripts/smoke_chat_task_flow.py --base-url http://127.0.0.1:8000

# 查看 DLQ 中的失败任务
python backend/scripts/read_chat_task_dlq.py --from-beginning --max-messages 5

# DLQ publish/read 最小 smoke 验收
python backend/scripts/smoke_chat_task_dlq_flow.py
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

当前与 Phase 5 入口保护直接相关的关键配置包括：

- `API_RATE_LIMIT_ENABLED`
- `API_RATE_LIMIT_WINDOW_SECONDS`
- `API_RATE_LIMIT_AUTH_MAX_REQUESTS`
- `API_RATE_LIMIT_CHAT_MAX_REQUESTS`
- `API_RATE_LIMIT_TASK_CREATE_MAX_REQUESTS`
- `AUTH_LOGIN_MAX_FAILED_ATTEMPTS`
- `AUTH_LOGIN_ATTEMPT_WINDOW_SECONDS`
- `AUTH_LOGIN_LOCK_SECONDS`
- `TOOL_CALL_TIMEOUT_SECONDS`
- `CALCULATOR_TOOL_TIMEOUT_SECONDS`
- `WEB_SEARCH_TOOL_TIMEOUT_SECONDS`
- `USER_ACTIVE_TASK_LIMIT`

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
- 已补最小登录失败保护：同一邮箱在窗口期内连续失败达到阈值后会被临时锁定，成功登录会清空失败计数

## 异步聊天任务策略
- 当前已支持“提交任务 + 轮询结果”模式
- API 负责创建 `chat task` 并投递到 `task broker`
- Worker 负责消费任务并执行带会话聊天链路，随后写回业务会话与任务结果
- 当前已补最小用户级并发保护：同一用户活跃任务数达到 `USER_ACTIVE_TASK_LIMIT` 后，再提新任务会返回 `429`
- 当前已补最小会话级串行保护：同一用户的同一 `session_id` 若已有 `queued/running` 任务，再次提交会返回 `409`
- 默认 broker 为进程内 `InMemory` 队列，便于本地直接运行
- 切换 `TASK_BROKER_BACKEND=kafka` 后，API 不再启动内置 worker，需要单独运行 `backend/scripts/run_task_worker.py`
- 仓库根目录已新增 `docker-compose.kafka-local.yml`，用于固定本地单机 `Postgres + Apache Kafka(KRaft)` 联调基线
- 可先运行 `python backend/scripts/run_task_worker.py --check` 检查当前 `consumer_mode` 是标准 `consumer_group` 还是本地 `direct_partition_fallback`
- 可继续运行 `python backend/scripts/run_task_worker.py --diagnose` 检查 Kafka broker 连通性、topic metadata 与 `__consumer_offsets` 可见性
- 可运行 `python backend/scripts/smoke_chat_task_flow.py` 执行最小全链路验收：注册、登录、建会话、提 task、轮询结果、查会话消息
- 当前已补最小重试与 DLQ：失败任务会按 `TASK_WORKER_MAX_RETRIES` 重试，超过次数后发布到 `KAFKA_CHAT_TASK_DLQ_TOPIC`
- 可运行 `python backend/scripts/read_chat_task_dlq.py` 直接查看 `KAFKA_CHAT_TASK_DLQ_TOPIC` 中的失败任务
- 可运行 `python backend/scripts/smoke_chat_task_dlq_flow.py` 直接做 DLQ publish/read 最小验收
- Kafka 模式依赖额外安装 `kafka-python`

## API 限流策略
- 当前先对高风险写接口做入口限流：
  - `POST /auth/register`
  - `POST /auth/login`
  - `POST /auth/refresh`
  - `POST /chat/agent`
  - `POST /chat/agent/session`
  - `POST /chat/agent/session/stream`
  - `POST /chat/tasks`
- 默认优先使用 `REDIS_URL` 对应的 Redis 作为共享计数存储；未配置或初始化失败时回退到进程内 `InMemory`
- 命中限流时返回 `429 Too Many Requests`，并附带：
  - `Retry-After`
  - `X-RateLimit-Limit`
  - `X-RateLimit-Remaining`

## 工具调用超时策略
- 当前已补最小 tool timeout 包装器
- `web_search_tool` 超时后不会无限阻塞，而是返回受控的超时结果：
  - `count=0`
  - `sources=[]`
  - `error=timeout`
- `calculator_tool` 超时会直接报错，避免表达式执行异常长期占住链路

## 日志脱敏策略
- 当前已补最小日志脱敏能力，统一在日志格式层生效
- 默认会脱敏以下常见敏感信息：
  - 邮箱
  - `password`
  - `access_token`
  - `refresh_token`
  - `Authorization` / `Bearer token`
  - JWT 形态 token

## 审计日志策略
- 当前已补最小审计日志能力，默认写入 `audit_store`
- 当前优先记录的关键事件包括：
  - `auth.register`
  - `auth.login`
  - `auth.refresh`
  - `auth.logout`
  - `chat.task.create`
  - `chat.task.failed`
