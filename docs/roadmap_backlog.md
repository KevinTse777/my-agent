# StudyMate Agent 路线图与任务清单（Backlog）

本 Backlog 以 `docs/industrial_product_plan.md` 为基线，拆分为 Epic → Story/Task 的可执行条目，默认按 16 周规划组织。

字段说明：
- **Priority**：P0（必须）/ P1（重要）/ P2（可延后）
- **Owner**：建议角色（Backend/Frontend/DevOps/QA/Sec）
- **Acceptance**：验收口径（可测试、可观察、可回滚）

---

## Epic A：工程治理基线（Phase 0）

### A1 代码与目录职责规范（P0）
- **Owner**：Backend
- **Tasks**
  - 定义 `routers/services/tools/core/schemas/tests` 的职责边界与依赖方向
  - 约束：禁止 `tools` 直接依赖 `routers`；`routers` 不承载业务逻辑
- **Acceptance**
  - 新增模块能被清晰归类；无跨层反向依赖

### A2 配置与密钥治理（P0）
- **Owner**：Backend/Sec
- **Tasks**
  - 统一 `settings` 读取与校验策略（缺失即 fail fast）
  - `.env.example` 标准化：分组、描述、默认值策略
  - 明确敏感信息日志脱敏规则
- **Acceptance**
  - 任一环境可一键启动（仅需填 env）
  - 日志中不出现 key/token/PII

### A3 CI 基线（P0）
- **Owner**：DevOps
- **Tasks**
  - 建立 CI：格式化/静态检查/单测/构建
  - main 分支合并门禁：CI 必须绿
- **Acceptance**
  - 失败用例阻断合并；有清晰失败提示

### A4 变更与发布模板（P1）
- **Owner**：DevOps/Backend
- **Tasks**
  - PR 模板：变更范围、风险、回滚、测试证据
  - Release note 模板：版本号、变更摘要、兼容性说明
- **Acceptance**
  - 每次变更可追溯；上线具备回滚说明

---

## Epic B：后端可维护性重构（Phase 1）

### B1 `agent_service` 职责拆分（P0）
- **Owner**：Backend
- **Deliverables**
  - `agent_factory.py`：模型与 agent 构建（含缓存策略）
  - `agent_runner.py`：阻塞/会话/流式执行入口
  - `event_parser.py`：token/tools/sources 提取与去重
  - `memory_manager.py`：memory store 选择、load/append、降级策略
- **Acceptance**
  - 对外 API 行为不变（接口与响应字段兼容）
  - 模块可单测（无隐式全局状态耦合）

### B2 统一异常模型与错误码（P0）
- **Owner**：Backend
- **Tasks**
  - 定义错误码：模型调用、工具调用、存储、参数校验、限流
  - 统一 API 返回格式（含 `request_id`、`error_code`）
- **Acceptance**
  - 任一失败响应可通过错误码分类；前端可据此提示/重试

### B3 Tool 执行包装器（P0）
- **Owner**：Backend
- **Tasks**
  - 为每个 tool 增加：timeout、重试（指数退避）、最大重试次数、熔断阈值
  - 统一 tool 输出结构（成功/失败语义一致）
- **Acceptance**
  - 外部依赖波动时系统可降级，不雪崩

### B4 测试补齐（P0）
- **Owner**：Backend/QA
- **Tasks**
  - 单测：parser、dedup、异常分支、tool wrapper
  - 集成：会话接口 + memory（inmemory/postgres 可选）+ tool mock
- **Acceptance**
  - 核心链路覆盖率目标：>= 70%（可先以关键模块为准）

---

## Epic C：可观测性与稳定性（Phase 2）

### C1 结构化日志规范（P0）
- **Owner**：Backend/DevOps
- **Tasks**
  - 统一字段：`request_id/session_id/task_id/user_id(optional)`、`tool_name`、`duration_ms`
  - 统一日志级别与采样策略（避免 token/内容泄露）
- **Acceptance**
  - 任一请求可通过 `request_id` 串起关键节点日志

### C2 指标与面板（P0）
- **Owner**：DevOps
- **Tasks**
  - 指标：QPS、P95、错误率、TTFT、tool 成功率、队列堆积（后续）
  - 成本：token/请求、工具调用次数/请求
- **Acceptance**
  - 有可用 dashboard；异常阈值可配置

### C3 分布式追踪（P1）
- **Owner**：Backend/DevOps
- **Tasks**
  - OTel：贯通 API → Agent → Tool（至少 span 层级）
- **Acceptance**
  - 任一请求可查看耗时分解（模型 vs 工具 vs 存储）

### C4 告警与演练（P0）
- **Owner**：DevOps/Backend
- **Tasks**
  - 告警：错误率、延迟、成本突增、外部依赖不可用
  - 演练：一次降级演练 + 一次回滚演练
- **Acceptance**
  - 触发告警后 5 分钟内可定位；有 SOP

---

## Epic D：异步任务中心与水平扩展（Phase 3）

### D1 任务模型与状态机（P0）
- **Owner**：Backend
- **Tasks**
  - Task 状态：`queued/running/succeeded/failed/cancelled`
  - 幂等：`task_key` 去重策略
  - 结果存储：摘要 + 事件流（用于前端展示）
- **Acceptance**
  - 同一任务重复提交不产生重复执行（或有明确策略）

### D2 队列与 worker（P0）
- **Owner**：Backend/DevOps
- **Tasks**
  - 引入任务队列（优先 Redis）
  - Worker 独立进程：并发控制、超时、重试、隔离
- **Acceptance**
  - API 与 worker 可独立扩缩容；worker 挂掉不影响 API 健康

### D3 异步接口与前端对接（P1）
- **Owner**：Backend/Frontend
- **Tasks**
  - `POST /tasks` 创建任务；`GET /tasks/{id}` 拉取状态；（可选）SSE/WebSocket 推送
  - 前端：任务列表、状态展示、失败重试入口
- **Acceptance**
  - 端到端：提交→执行→完成→展示，全链路跑通

---

## Epic E：生产化发布与安全治理（Phase 4）

### E1 容器化与环境分层（P0）
- **Owner**：DevOps
- **Tasks**
  - Docker 镜像：api/worker
  - 环境：dev/staging/prod 配置隔离
- **Acceptance**
  - 一键部署到 staging；prod 与 staging 差异最小化

### E2 灰度与回滚（P0）
- **Owner**：DevOps
- **Tasks**
  - 灰度发布策略（按比例/按用户/按路由）
  - 回滚脚本与数据兼容策略
- **Acceptance**
  - 10 分钟内可回滚；回滚不丢关键状态

### E3 安全加固（P0）
- **Owner**：Sec/Backend
- **Tasks**
  - 密钥轮转流程
  - 依赖与漏洞扫描（最低限度）
  - 审计日志：管理操作、配置变更、发布记录
- **Acceptance**
  - 能回答“谁在何时做了什么变更”

---

## 建议的 P0 最小集合（首月必须完成）
- A2 / A3
- B1 / B2 / B3 / B4（可先覆盖关键模块）
- C1 / C2 / C4（先 MVP）

最后更新：2026-03-31
