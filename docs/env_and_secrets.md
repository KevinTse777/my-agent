# Environment & Secrets 规范（Epic A）

本文件定义环境变量分级、密钥管理和日志脱敏要求。

## 1. 环境变量分级

### 必填（生产）

- `DASHSCOPE_API_KEY`：模型密钥
- `MODEL_NAME`：默认模型名
- `DASHSCOPE_BASE_URL`：模型网关地址

### 条件必填（按能力启用）

- `TAVILY_API_KEY`：启用 Web 搜索工具时必填
- `POSTGRES_URL`：启用持久会话记忆时必填
- `REDIS_URL`：启用缓存/上下文加速时必填

### 可选（默认值存在）

- `MEMORY_CONTEXT_WINDOW`（默认 `12`）
- `MEMORY_CONTEXT_TTL_SECONDS`（默认 `1800`）
- `VITE_API_BASE_URL`（默认 `/api`）
- `VITE_API_TIMEOUT`（默认 `60000`）
- `VITE_CHAT_ENDPOINT`（默认 `/chat/agent`）

## 2. 配置加载约束

- 所有变量通过 `.env` 或运行时注入，不允许硬编码密钥。
- 缺失必填项应在服务启动或首次调用前明确报错（fail fast）。
- `.env.example` 仅保留占位值，不得出现真实密钥。

## 3. 密钥管理要求

- 生产密钥通过密钥管理系统或 CI Secret 注入。
- 密钥轮转建议周期：90 天。
- 严禁在 issue、PR、日志、截图中暴露密钥片段。

## 4. 日志脱敏要求

禁止输出：

- 完整 API Key / Token
- 用户隐私信息（手机号、邮箱、身份证、地址）
- 原始授权头

允许输出（示例）：

- `request_id`, `session_id`, `task_id`
- 工具名、耗时、错误码
- 脱敏后主机名/路径

## 5. 手动操作清单（GitHub）

以下项无法通过代码仓库强制，需要仓库管理员在 GitHub 设置中完成：

- 开启 `main` 分支保护（Require status checks）
- 仅允许 CI 通过后合并
- 禁止直接 push 到 `main`
- 至少 1 名 reviewer 才可合并

