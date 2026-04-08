# Agent.md

本文件面向进入本仓库协作的开发代理或工程同学，帮助快速理解项目目标、架构边界与安全修改方式。

## 1. 项目概览

- 项目名称：`StudyMate Agent (Slim Edition)`
- 形态：前后端分离的学习助手
- 前端：`Vue 3 + Vite`
- 后端：`FastAPI + LangChain Agent`
- 当前核心能力：
  - 单轮对话
  - 带会话记忆的多轮对话
  - 工具调用（计算、Web 搜索）


## 2. 当前对外接口

后端主要接口：

- `GET /`
- `GET /health`
- `POST /chat/agent`
- `POST /chat/agent/session`
- `POST /chat/agent/session/stream`

前端默认通过 Vite 代理的 `/api` 前缀访问后端。

## 3. 仓库结构

```txt
my-agent/
├─ README.md
├─ Agent.md
├─ docs/
│  ├─ architecture.md
│  ├─ engineering_guardrails.md
│  ├─ env_and_secrets.md
│  ├─ industrial_product_plan.md
│  └─ roadmap_backlog.md
├─ backend/
│  ├─ README.md
│  ├─ init_chat_memory.sql
│  ├─ pytest.ini
│  ├─ scripts/
│  └─ app/
│     ├─ main.py
│     ├─ core/
│     ├─ routers/
│     ├─ services/
│     ├─ schemas/
│     ├─ tools/
│     └─ tests/
└─ frontend/
   ├─ README.md
   ├─ package.json
   └─ src/
```

## 4. 后端分层职责

必须优先遵守 `docs/engineering_guardrails.md` 中的边界约束。

- `backend/app/routers`
  - 只处理 HTTP 入口、参数校验、调用 service、组织响应
  - 不写业务编排，不直接访问数据库或外部工具
- `backend/app/services`
  - 业务与 Agent 编排层
  - 负责流程、策略、异常归一、跨组件组合
- `backend/app/tools`
  - 外部能力封装层
  - 提供稳定输入输出，负责超时、失败语义和第三方集成
- `backend/app/core`
  - 配置、日志、中间件等横切能力
- `backend/app/schemas`
  - 请求/响应模型
  - 不承载业务逻辑
- `backend/app/tests`
  - 关键路径与异常路径测试

允许依赖方向：

`routers -> services -> tools/core`

补充规则：

- `routers` 可依赖 `schemas`、`services`、`core`
- `services` 可依赖 `tools`、`core`、`schemas`
- `tools` 只能依赖 `core` 与第三方 SDK
- `tools` 禁止依赖 `routers`
- `schemas` 不依赖 `services` 或 `tools`

## 5. 前端职责

- `frontend/src` 负责 UI、交互和接口调用
- 前端不应承载后端业务规则
- 默认通过 `src/api/` 下的接口封装访问后端

如果修改接口结构，应同步检查：

- 前端 API 调用层
- 聊天消息渲染组件
- 来源链接或流式响应展示逻辑

## 6. 核心链路理解

核心调用路径如下：

`Frontend -> /api -> FastAPI routers -> chat_service -> agent_service -> LangChain Agent -> tools`

会话记忆策略：

- 优先 `Postgres + Redis`
- 其次 `Postgres`
- 最后回退 `InMemory`

这意味着涉及会话能力的改动时，需要特别注意：

- `session_id` 的传递是否稳定
- 存储不可用时的回退行为
- 非流式和流式接口的行为是否一致

## 7. 本地启动

后端依赖安装示例：

```bash
pip install fastapi "uvicorn[standard]" openai python-dotenv \
  langchain langchain-openai langgraph tavily-python psycopg[binary] psycopg-pool redis
```

启动后端：

```bash
uvicorn app.main:app --reload --app-dir backend --port 8000
```

启动前端：

```bash
cd frontend
npm install
npm run dev
```

默认前端地址：

- `http://127.0.0.1:5173`

## 8. 环境变量

从根目录 `.env.example` 复制出 `.env` 后再运行项目。

关键变量包括：

- `DASHSCOPE_API_KEY`
- `TAVILY_API_KEY`
- `POSTGRES_URL`
- `REDIS_URL`
- `VITE_API_BASE_URL`

除非用户明确要求，否则不要在仓库中写入真实密钥。

## 9. 修改原则

进行开发时，请优先遵守以下原则：

- 新功能优先落在 `services`，避免把业务逻辑堆进 `routers`
- 新外部能力优先新增到 `tools`，不要在 `services` 里直接散落 HTTP 请求
- 如果修改模型调用链、会话存储或响应结构，必须评估兼容性与回滚方式
- 如果新增核心功能，应补测试
- 如果是高风险改动，应补结构化日志字段，例如 `request_id`、`session_id`、`task_id`

不建议的做法：

- 在 `routers` 中直接编排 Agent 逻辑
- 在 `frontend` 中硬编码后端内部规则
- 为了快速修复而绕过现有服务分层

## 10. 验证方式

后端基础验证：

```bash
python -m compileall -q backend/app
```

测试：

```bash
cd backend
python -m pytest -q
```

如果改动影响前端联调，建议额外验证：

- 首页是否可打开
- 聊天请求是否成功
- 会话模式是否可持续发送消息
- 流式接口是否仍按预期返回

## 11. 文档优先级

当多个文档存在重叠时，建议按以下优先级理解项目：

1. `docs/engineering_guardrails.md`：职责边界与依赖规则
2. `docs/architecture.md`：整体结构与链路
3. `README.md`：项目概览与启动方式
4. `backend/README.md` / `frontend/README.md`：子模块说明
5. `docs/roadmap_backlog.md` 与 `docs/industrial_product_plan.md`：后续规划

## 12. 适合代理优先处理的任务

- 保持现有聊天链路稳定
- 在不破坏分层的前提下补充能力
- 修复前后端接口不一致问题
- 为关键服务增加测试
- 为会话记忆与流式返回补充健壮性处理

## 13. 修改前自检清单

开始改动前，先快速确认：

- 是否改在了正确目录层级
- 是否影响前端当前已使用接口
- 是否影响会话记忆回退策略
- 是否需要同步更新测试或 README
- 是否会引入新的密钥、外部依赖或部署成本

如果无法确定，优先保守修改，保持主链路可用。
