# StudyMate Agent API

[![CI](https://github.com/<YOUR_GITHUB_NAME>/<YOUR_REPO>/actions/workflows/ci.yml/badge.svg)](https://github.com/<YOUR_GITHUB_NAME>/<YOUR_REPO>/actions/workflows/ci.yml)

基于 **FastAPI + LangChain + Tool Calling + Agent** 的学习助手后端项目。

项目目标：从最小聊天接口起步，逐步升级到可工具调用、可观测、可测试、可扩展的 Agent 服务。

## 项目亮点

- FastAPI API 服务与 Swagger 文档
- 基础聊天、Chain、Tool Calling、Agent 全链路实践
- 工具层支持：计算器、模拟搜索、真实 Web 搜索（Tavily）
- 支持会话化 Agent（`session_id`）
- 统一异常响应（含 `request_id`）
- 请求日志 + 工具日志（耗时与成功/失败）
- pytest 接口测试 + GitHub Actions CI

## 技术栈

- Python 3.11+
- FastAPI / Uvicorn
- LangChain / langchain-openai / langgraph
- OpenAI SDK（阿里百炼 OpenAI 兼容模式）
- Tavily Python SDK
- Pydantic
- python-dotenv
- pytest

## 项目结构

```txt
my-agent/
├─ .github/workflows/ci.yml
├─ .env
├─ .gitignore
├─ README.md
└─ backend/
   ├─ pytest.ini
   └─ app/
      ├─ main.py
      ├─ llm_chain.py
      ├─ tool_calling.py
      ├─ agent_service.py
      ├─ core/
      │  ├─ config.py
      │  └─ logging.py
      ├─ routers/
      │  ├─ system.py
      │  └─ chat.py
      ├─ services/
      │  └─ chat_service.py
      ├─ schemas/
      │  └─ api_response.py
      ├─ tools/
      │  ├─ calculator.py
      │  ├─ search_mock.py
      │  ├─ search_web.py
      │  └─ langchain_tools.py
      └─ tests/
         └─ test_api.py
```

## 环境变量

在项目根目录创建 `.env`：

```env
DASHSCOPE_API_KEY=your_dashscope_key
MODEL_NAME=qwen-plus
DASHSCOPE_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
TAVILY_API_KEY=your_tavily_key
REDIS_URL=redis://localhost:6379/0
POSTGRES_URL=postgresql+psycopg://user:password@localhost:5432/studymate
MEMORY_CONTEXT_WINDOW=12
MEMORY_CONTEXT_TTL_SECONDS=1800
```

说明：
- `DASHSCOPE_*` 用于百炼 OpenAI 兼容调用。
- `TAVILY_API_KEY` 用于真实 Web 搜索工具。
- `REDIS_URL` / `POSTGRES_URL` 预留给会话记忆持久化（当前版本可不填）。
- `MEMORY_CONTEXT_WINDOW` / `MEMORY_CONTEXT_TTL_SECONDS` 控制短期上下文窗口与 TTL（当前内存实现先使用窗口值）。

## 本地启动

```bash
pip install fastapi "uvicorn[standard]" openai python-dotenv langchain langchain-openai langgraph tavily-python pytest
uvicorn app.main:app --reload --app-dir backend --port 8000
```

访问：
- Root: `http://127.0.0.1:8000/`
- Health: `http://127.0.0.1:8000/health`
- Docs: `http://127.0.0.1:8000/docs`

提示：
- 访问 `GET /` 现在会返回服务信息，不会 404。
- 若端口冲突报 `Address already in use`，改用 `--port 8001` 或先释放 8000 端口。

## API 概览

- `GET /`
- `GET /health`
- `POST /chat/simple`
- `POST /chat/chain`
- `POST /tools/calculate`
- `POST /chat/manual`
- `POST /chat/auto-tool`
- `POST /chat/agent`
- `POST /chat/agent/session`
- `POST /tools/web-search`

## 示例请求

### Agent

```bash
curl -X POST "http://127.0.0.1:8000/chat/agent" \
  -H "Content-Type: application/json" \
  -d '{"message":"请计算 (18+24)/7"}'
```

### Web 搜索工具

```bash
curl -X POST "http://127.0.0.1:8000/tools/web-search" \
  -H "Content-Type: application/json" \
  -d '{"query":"FastAPI official docs"}'
```

## 统一响应结构

除 `GET /health` 外，大多数接口统一返回：

```json
{
  "success": true,
  "message": "ok",
  "data": {}
}
```

## 系统架构（简化）

- Router：请求入口、参数校验、HTTP 返回
- Service：业务编排（chat/tool/agent/session）
- Tools：可被模型调用的能力函数
- LangChain：chain 与 agent 推理流程
- Core：配置管理与日志中间件

请求流：`Client -> Router -> Service -> (LangChain Agent -> Tools) -> Response`

## 可观测性

- 每个请求生成 `request_id`，写入响应头 `X-Request-ID`
- 请求日志包含：方法、路径、状态码、耗时
- 工具日志包含：工具名、输入、耗时、成功/失败
- 统一错误响应结构：

```json
{
  "success": false,
  "message": "...",
  "data": null,
  "request_id": "..."
}
```

## 测试与 CI

本地测试：

```bash
cd backend
pytest -q app/tests/test_api.py
```

CI：
- GitHub Actions 在 push / pull_request 自动执行测试
- 工作流文件：`.github/workflows/ci.yml`

## 当前限制

- `session` 为内存存储，服务重启后会丢失
- 外部搜索能力依赖 Tavily key 和网络可用性
- 部分 Agent 行为存在模型非确定性

## 后续可扩展方向

- Redis 持久化会话
- RAG 知识库工具
- 更严格的来源追踪与答案引用
- Docker 化与部署
- 更细粒度测试（mock LLM/tool 层）

## License

MIT
