# Agent 项目升级实施路线图（UPGRADE_PLAN）

## 1. 项目目标与当前基线

### 目标
- 将当前“可用聊天 Agent”升级为“可解释、可扩展、可评估”的工程化 Agent 平台。
- 优先提升能力可信度与架构表达力，支持后续简历与面试展示。

### 当前基线（已具备）
- 前后端分离：`Vue 3 + Vite`、`FastAPI + LangChain Agent`。
- 能力链路：单轮/会话对话、工具调用（计算与 Web 搜索）、流式输出。
- 会话记忆：`Redis + Postgres + InMemory` 回退策略。
- 基础工程能力：统一响应结构、请求日志、测试与 CI。

### 当前主要缺口
- 推理过程缺乏清晰编排（复杂任务稳定性与可解释性不足）。
- 上下文管理缺乏“摘要 + 事实槽位”分层能力。
- Skill 能力尚未形成统一注册与前后端联动。
- MCP 生态未接入，外部能力扩展边界不清晰。

## 2. 总体架构升级图（文本版）

```text
User / Frontend
  -> Session + Skill Mode + Stream Viewer
  -> FastAPI Router (/chat/agent/session, /stream)
  -> Chat Service
  -> Reasoning Orchestrator
       -> Planner (Plan-and-Solve trigger)
       -> ReAct Executor (hidden reasoning)
       -> Tool Dispatcher
            -> Local Tools (calculator, web_search, ...)
            -> MCP Gateway (fetch, filesystem-readonly)
       -> Observer / Step Recorder (safe summary only)
  -> Context Manager
       -> Recent Window
       -> Session Summary
       -> Facts Slots
  -> Memory Store (Redis + Postgres + InMemory fallback)
  -> Response Builder
       -> answer / tools_used / sources
       -> reasoning_summary / context_meta
       -> stream events: plan / step / token / tool / sources / end / error
```

## 3. Phase 1：推理编排（隐式 ReAct + Plan-and-Solve 触发）

### 目标
- 增加可控推理编排层，提升复杂问题处理稳定性。
- 保留隐式 ReAct，不暴露原始 chain-of-thought，仅输出安全摘要。

### 具体改动（后端/前端/接口）
- 后端：
  - 新增 `ReasoningOrchestrator` 负责 `plan -> act -> observe -> final` 状态流转。
  - 增加复杂任务判定器（长度、意图、工具需求）触发 Plan-and-Solve。
  - 为每次执行产生结构化步骤记录（内部使用）。
- 前端：
  - 暂不改主交互；保留兼容，后续在流式阶段消费 `plan/step` 事件。
- 接口：
  - 响应预留 `reasoning_summary` 字段（字符串数组）。
  - 流式协议预留 `plan`、`step` 事件类型。

### 验收标准
- 功能验证：复杂问题可先规划再执行，输出步骤摘要而非原始思维链。
- 稳定性验证：工具调用失败时可回退，仍能返回可用结论或清晰错误。

### 预计工时
- 1.5 ~ 2.5 天

### 依赖与风险
- 依赖：现有 `agent_service` 与工具层保持可复用。
- 风险：过度规划导致延迟上升；需通过阈值与超时策略控制。

## 4. Phase 2：分层上下文（窗口/摘要/事实槽位）

### 目标
- 构建分层上下文机制，降低 token 成本并增强长对话一致性。

### 具体改动（后端/前端/接口）
- 后端：
  - 新增 `ContextManager`，统一组装 `recent_window + session_summary + facts_slots`。
  - 增加摘要更新策略（例如每 4~6 轮更新一次）。
  - 新增长期事实槽位（目标、偏好、约束、已完成事项）。
  - 增加 token 预算裁剪策略。
- 前端：
  - 可选展示“上下文增强中”状态，不阻断主流程。
- 接口：
  - 响应新增 `context_meta`：是否使用摘要、事实条目数、窗口条数等。

### 验收标准
- 功能验证：跨多轮任务中，模型能持续引用已确认的目标与约束。
- 稳定性验证：长对话下响应不明显退化，超长上下文仍可稳定返回。

### 预计工时
- 2 ~ 3 天

### 依赖与风险
- 依赖：Phase 1 编排层稳定后接入最合适。
- 风险：摘要偏差导致语义漂移；需增加摘要回写与人工抽查样例。

## 5. Phase 3：双层 Skill（后端 Skill Registry + 前端模式映射）

### 目标
- 建立可扩展 Skill 机制，实现“后端能力模板化 + 前端模式化选择”。

### 具体改动（后端/前端/接口）
- 后端：
  - 新增 Skill Registry：`skill_id -> prompt_patch + tool_allowlist + output_style`。
  - 调度链路在执行前注入 skill 配置并做工具权限控制。
  - 提供默认 `general` skill，保证兼容。
- 前端：
  - 增加模式选择器（如 `general`、`study`、`coding`、`research`）。
  - 选择结果随请求发送 `skill_id`。
- 接口：
  - 请求新增可选字段 `skill_id`（snake_case）。

### 验收标准
- 功能验证：不同 skill 下回答风格、工具选择策略明显区分。
- 稳定性验证：非法/缺失 skill_id 不影响主流程，回落默认模式。

### 预计工时
- 1.5 ~ 2.5 天

### 依赖与风险
- 依赖：Phase 1 编排层可注入策略，Phase 2 上下文可被复用。
- 风险：skill 边界不清导致行为重叠；需定义最小差异化规范。

## 6. Phase 4：MCP 最小接入（2 个服务 + 安全边界）

### 目标
- 以最小闭环接入 MCP，验证协议兼容、容错、权限与观测能力。

### 具体改动（后端/前端/接口）
- 后端：
  - 新增 `MCPGateway` 统一对接、超时、重试、错误归一化。
  - 首期接入 2 个服务：
    - `fetch`（通用抓取/检索补充）
    - `filesystem` 只读访问（限定白名单目录）
  - 工具分发层统一本地工具与 MCP 工具调用协议。
  - 增加安全控制：工具白名单、参数校验、只读路径限制、熔断。
- 前端：
  - 可选展示工具来源标签（local / mcp），不改变主交互。
- 接口：
  - 无强制新增字段；沿用 `tools_used` 并在 debug 信息中区分来源。

### 验收标准
- 功能验证：MCP 工具可被调度并返回结构化结果。
- 稳定性验证：MCP 故障时可降级到本地能力，不导致整体不可用。

### 预计工时
- 2 ~ 3 天

### 依赖与风险
- 依赖：Phase 1 的调度与步骤记录机制。
- 风险：第三方服务不稳定；需有超时与降级兜底策略。

## 7. 可观测性与评估指标（延迟、命中率、降级成功率）

### 指标定义
- 延迟：
  - 首 token 延迟（stream 首次输出时间）
  - 端到端响应时延（非流式/流式完成）
- 工具命中率：
  - 需要工具的问题中，正确触发工具的比例
  - 工具调用成功率与有效结果率
- 降级成功率：
  - 外部依赖（MCP/搜索）失败场景下仍返回可用答复比例
- 质量稳定性：
  - 多轮复杂任务完成率
  - 事实一致性（与 facts slots 对齐率）

### 观测实施建议
- 日志统一追加：`request_id`、`session_id`、`skill_id`、`phase`、`tool_source`、耗时指标。
- 指标按周出基线，形成“升级前后对比”用于简历与面试证明。

## 8. 风险与回滚策略

### 主要风险
- 推理编排复杂度上升，影响时延与维护成本。
- 摘要/事实抽取误差导致上下文偏移。
- Skill 与 MCP 叠加后，权限与安全边界复杂化。

### 回滚策略
- 以 Feature Flag 控制每个 Phase：可单独开启/关闭。
- 保留现有基础链路作为 fallback：
  - 关闭 Orchestrator 时回退原 `agent.invoke`。
  - 关闭分层上下文时仅使用 recent window。
  - 关闭 MCP 时仅调用本地工具。
- 每个阶段上线后至少保留 1 周观察窗口，再推进下一阶段。

---

## 首批接口契约（仅规划，不改代码）

### 请求体（可选新增）
- `skill_id: string`
- `debug_trace: boolean`

### 响应体（新增）
- `reasoning_summary: string[]`
- `context_meta: object`
  - `summary_used: boolean`
  - `facts_used: number`
  - `window_messages: number`

### 流式事件（新增）
- `plan`
- `step`

> 命名规则采用 snake_case，与现有接口风格一致。

---

## 分步执行清单（可打勾）

- [ ] Step 1: 推理编排骨架（隐式 ReAct + Plan-and-Solve 触发）
- [ ] Step 2: 上下文摘要与事实槽位（分层 Context Manager）
- [ ] Step 3: Skill Registry 与前端模式映射（双层 Skill）
- [ ] Step 4: MCP Gateway 与双服务接入（fetch + filesystem readonly）
- [ ] Step 5: 测试与指标基线（可观测性 + 对比评估）

