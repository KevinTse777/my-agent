# StudyMate Agent API

一个用于学习 **FastAPI + LangChain + Tool Calling + Agent** 的后端项目。

项目目标是：用循序渐进的方式，从最小聊天接口开始，逐步演进到可调用工具、可维护、可扩展的 Agent 后端服务。

## 项目亮点

- 使用 FastAPI 提供标准 REST API
- 支持基础聊天（`/chat/simple`）
- 支持 LangChain chain 调用（`/chat/chain`）
- 支持手动工具调用（`/tools/calculate`）
- 支持模型自动 tool calling（`/chat/auto-tool`）
- 支持 LangChain Agent（`/chat/agent`）
- 支持基于 `session_id` 的最小会话记忆（内存版，`/chat/agent/session`）
- 使用 `.env` 管理模型配置
- 按 `routers / services / tools / schemas / core` 做结构拆分

## 技术栈

- Python 3.11+
- FastAPI
- Uvicorn
- LangChain
- langchain-openai
- OpenAI Python SDK（以阿里百炼 OpenAI 兼容模式调用）
- Pydantic
- python-dotenv

## 目录结构

```txt
my-agent/
├─ .env
├─ .gitignore
├─ README.md
└─ backend/
   └─ app/
      ├─ main.py
      ├─ llm_chain.py
      ├─ tool_calling.py
      ├─ agent_service.py
      ├─ core/
      │  └─ config.py
      ├─ routers/
      │  ├─ system.py
      │  └─ chat.py
      ├─ services/
      │  └─ chat_service.py
      ├─ schemas/
      │  └─ api_response.py
      └─ tools/
         ├─ calculator.py
         ├─ search_mock.py
         └─ langchain_tools.py
```

## 环境变量配置

在项目根目录创建 `.env`：

```env
DASHSCOPE_API_KEY=your_dashscope_key
MODEL_NAME=qwen-plus
DASHSCOPE_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
```

说明：
- 使用阿里百炼 OpenAI 兼容模式时，需要设置 `DASHSCOPE_BASE_URL`。
- `MODEL_NAME` 请替换为你账号可用模型。

## 安装与启动

1. 创建并激活虚拟环境（你当前使用 conda 也可以）
2. 安装依赖
3. 启动服务

```bash
pip install fastapi "uvicorn[standard]" openai python-dotenv langchain langchain-openai langgraph
uvicorn app.main:app --reload --app-dir backend --port 8000
```

启动后访问：
- 健康检查: `http://127.0.0.1:8000/health`
- Swagger 文档: `http://127.0.0.1:8000/docs`

## API 一览

### 1) 健康检查

- `GET /health`

示例响应：

```json
{"status":"ok"}
```

### 2) 基础聊天（直连模型）

- `POST /chat/simple`

请求体：

```json
{"message":"什么是 FastAPI？"}
```

### 3) LangChain Chain 聊天

- `POST /chat/chain`

请求体：

```json
{"message":"解释一下什么是 prompt template"}
```

### 4) 手动工具调用（计算器）

- `POST /tools/calculate`

请求体：

```json
{"expression":"(12+8)/5"}
```

### 5) 手动模式聊天（chat/calculator）

- `POST /chat/manual`

请求体：

```json
{"mode":"chat","message":"请解释 chain"}
```

或

```json
{"mode":"calculator","message":"(2+3)*4"}
```

### 6) 自动 tool calling

- `POST /chat/auto-tool`

请求体：

```json
{"message":"请计算 (23.5+18.5)*3"}
```

### 7) LangChain Agent

- `POST /chat/agent`

请求体：

```json
{"message":"请解释 LangChain 是什么"}
```

### 8) 带会话记忆的 Agent

- `POST /chat/agent/session`

请求体：

```json
{"session_id":"u1","message":"我在学 FastAPI，帮我安排 3 天学习计划"}
```

## 当前实现说明

- 会话记忆使用进程内存保存，服务重启后会丢失。
- `search_mock` 是教学用模拟检索工具，后续可替换为真实搜索 API。
- 项目以“先跑通，再工程化”方式演进，适合作为学习与简历项目基础。

## 下一步可扩展方向

- 接入真实搜索工具（Tavily / SerpAPI / 自建检索）
- 增加课程知识库工具（RAG）
- 会话存储升级为 Redis/数据库
- 增加日志与链路追踪（LangSmith）
- Docker 化与部署
- 增加接口测试（pytest + httpx）

## License

MIT
