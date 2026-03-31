# StudyMate Agent - 面试高频追问清单（含参考答案）

适用范围：你简历中提到的技术栈（Python / FastAPI / LangChain / LLM Tool Calling / PostgreSQL / Redis）以及当前“瘦身版 MVP”的能力：单轮、会话、多会话会记忆、流式输出、工具调用、来源可解释性。

> 备注：以下“参考答案”是面试官常见追问视角。你在回答时可以优先讲“你的取舍 + 你如何保证正确性/稳定性 + 你怎么验证”，再补充实现细节。

---

## 1. 架构与主链路

### Q1. 你在 `router`、`chat_service`、`agent_service` 各自承担什么职责？为什么这样分层？

**参考答案要点：**

- `router`：做请求/参数校验（Pydantic）、补充 `request_id`，并负责把结果包装成统一响应结构；流式端点负责把后端事件流转成 `NDJSON`（`StreamingResponse`）。
- `chat_service`：提供同步/流式的“入口适配层”（例如 `agent_chat` / `agent_session_chat` / `agent_session_chat_stream`），把路由参数原样传给 `agent_service`，尽量保持接口简单。
- `agent_service`：真正的编排与落地层。包括：
  - 构建 LangChain Agent（`_build_agent`）
  - 构建记忆存储（`_build_memory_store`）
  - 注入会话上下文（`memory_store.load_context`）
  - 执行 Agent（`invoke` 或 `astream_events`）
  - 解析输出结构为 `answer/tools_used/sources`

### Q2. LangChain 的工具调用是怎么发生的？工具是如何被模型“决定调用”的？

**参考答案要点：**

- 使用 LangChain 的工具机制：在 `_build_agent()` 里把 `tools=[calculator_tool, web_search_tool]` 传给 `create_agent`。
- `calculator_tool` 与 `web_search_tool` 都用 `@tool` 装饰成标准工具函数，工具参数/返回值由函数签名定义。
- 模型在生成过程中根据指令与用户问题决定是否需要工具；当需要时，会触发 tool call，随后由 LangChain 执行对应工具。
- 在流式链路里可以观察事件：`on_tool_start` / `on_tool_end`，其中 `event["name"]` 对应工具名；这也用于构建 `tools_used`。

### Q3. 你如何保证 `answer/tools_used/sources` 在三种接口里语义一致？

**参考答案要点：**

- 我先把这三个字段当成统一的“业务输出模型”：`answer` 始终是最终给用户看的完整回复文本，`tools_used` 是这次回答过程中实际调用过的工具名列表（去重后），`sources` 是这次回答背后的外部信息来源列表（例如网页的 `title/url/snippet`）。
- 单轮接口（`POST /chat/agent`）和会话接口（`POST /chat/agent/session`）最终都通过同一个编排出口（例如 `run_agent` 或等价封装），复用同一段逻辑从 LangChain 的输出里抽取 `answer/tools_used/sources`，然后直接作为响应体返回，所以这两个接口在语义上天然是一致的。
- 流式接口（`POST /chat/agent/session/stream`）只是传输方式不同：中间阶段按 token 和中间 `sources` 事件往前端推送，但在流的终态会发出一个 `type="end"` 的事件，其中也包含完整的 `answer/tools_used/sources`，含义和非流式接口完全一致；前端只要统一把这个终态事件当作“等价于一次普通请求的最终结果”即可。
- 在工程上我会把“从 LangChain 事件/消息里解析出 `answer/tools_used/sources`”收敛到一个函数/类里，让三个接口都只调用这一处逻辑，并用 mock 事件分别跑非流式和流式的测试，来验证同一组输入在三种接口下得到的最终 `answer/tools_used/sources` 是一致的。

---

## 2. Tool Calling（计算与搜索）

### Q4. `calculator_tool` 和 `web_search_tool` 的输入/输出契约是什么？你如何保证模型不会传错参数？

**参考答案要点：**

- `calculator_tool(expression: str) -> str`：面向数学表达式，输入是字符串表达式；内部调用你实现的 `calculate()`，返回计算结果的字符串。
- `web_search_tool(query: str) -> str`：输入 `query`；内部调用 `search_web_structured(query, max_results=3)`，返回结构化结果的 JSON 字符串。
- “保证模型不会传错参数”的策略包括：
  - 工具函数签名明确（LangChain 工具调用会按签名路由参数）
  - 系统提示里要求计算必须走 `calculator_tool`（减少模型直接胡算）
  - 工具执行阶段出错会抛异常，由上层 fallback 或返回错误事件（面试时可补你正在考虑的超时/熔断增强）

### Q5. 如果模型调用了 `web_search_tool`，但最终返回结构里没有 `sources`，你系统会怎么表现？你怎么让它更稳？

**参考答案要点：**

- 当前实现里 sources 的提取依赖于“工具输出长得像 `{"sources":[...]}`”或事件 payload 中存在 `sources`。
- 一旦 payload 结构不匹配，sources 会变成空列表（不会直接报错），从而前端可能只得到 `answer`。
- 更稳的改进方向：
  - 统一工具输出契约：让 `web_search_tool` 永远返回固定 schema（例如明确 `{"sources":[...]}`），并在模型侧提示“必须按 schema 输出”
  - 在提取来源失败时加入日志与 debug trace（带 `request_id/session_id/tool_name`）
  - 对 `sources` 做 schema 校验，不通过则降级到“无来源但不影响答案”

### Q6. 如何处理“既需要计算又需要事实”的问题？工具路由策略是什么？

**参考答案要点：**

- 系统提示里区分两类需求：
  - “需要精确计算必须调用 calculator_tool”
  - “涉及最新事实/外部信息优先使用 web_search_tool”
- 对复合问题，agent 可能会先决定先算、再查或先查再算；你在面试时可以说：你依赖 agent 的规划/工具选择能力，并用 `tools_used` 与 `sources` 给出可解释性。

---

## 3. 流式输出协议（NDJSON）

### Q7. 你定义的 NDJSON 事件协议里，`start/token/sources/end/done` 各自触发条件是什么？前端以哪个事件作为完成依据？

**参考答案要点：**

- `router` 层先发 `{"type":"start", ...}`。
- 在 `agent_service.stream_agent_with_session()` 中：
  - `on_chat_model_stream` 把 token 逐段 yield 为 `{"type":"token","content":"..."}`。
  - `on_tool_end` / `on_chain_end` 若能提取 sources，会 yield `{"type":"sources","sources":[...]}`。
  - 最终会 yield `{"type":"end", "answer":..., "tools_used":..., "sources":...}`
- `router` 的 `finally` 又会 yield 一个 `{"type":"done", ...}` 作为路由级结束标记。
- 面试时建议你明确前端“只认一个完成信号”（当前你可以说现在你前端兼容两个终止事件，并建议后续统一协议）。

### Q8. 流式过程中异常时，你如何保证前端拿到最小可用信息？是否可恢复？

**参考答案要点：**

- 当前 router 会捕获 `ValueError` 和通用 `Exception`，并在流中 yield `{"type":"error", "message":..., "request_id":...}`。
- 在 `finally` 中仍会 yield 结束事件（`done`），保证前端不会一直等。
- 可恢复策略可表述为：前端收到 `error` 后可提示用户重试；后端也在 stream 函数里有 fallback 到 blocking invoke 的逻辑（只要模型能最终生成回答）。

### Q9. 你如何避免流式 token 拼接导致最终答案不完整或重复？（尤其是多个 AIMessage 场景）

**参考答案要点：**

- 当前流式实现策略是：在 `on_chat_model_stream` 中把每个 chunk 的 `content` 提取出来并 `final_chunks.append(token)`，最后在终态 `end` 事件里 `final_answer="".join(final_chunks).strip()`。
- 防重复/不完整风险的改进：
  - 确保只在 `on_chat_model_stream` 阶段拼接，不在其他阶段覆盖 final answer
  - 对 chunk content 做幂等处理（例如忽略空 token / 去重规则）
  - 明确“终态 answer”与 token 流一致性校验（例如记录 token 数/长度差异到日志）

---

## 4. 会话记忆（Redis / Postgres / InMemory）

### Q10. 你会话记忆是按什么粒度裁剪上下文的？具体规则是什么？

**参考答案要点：**

- 你在配置里使用 `memory_context_window`，并以“消息数”作为截断粒度：
  - `InMemoryStore.load_context`：返回该 `session_id` 最后 `max_history_messages` 条消息
  - `PostgresMemoryStore.load_context`：按 `id desc limit N` 查到最近 N 条，再 reverse 回正序
  - `HybridMemoryStore.load_context`：优先用 Redis；Redis 不存在时从 Postgres 加载，再写回 Redis；最终都只保留最近 N 条

### Q11. Hybrid（Redis+Postgres）下缓存与数据库一致性怎么保证？并发会有什么风险？

**参考答案要点：**

- 当前实现采用“写后更新”风格：
  - 写入时：先 `pg_store.append_turn(...)` 再把更新后的上下文写回 Redis
- 并发风险（你可以说出你知道的点）：
  - 并发写可能导致 Redis 覆盖成较旧上下文（典型的 last-write-wins）
  - 乱序导致历史顺序问题（例如两个请求同时写）
- 缓解方向（可作为加分项）：
  - Redis 写入使用版本号/时间戳（或基于数据库生成的序号）
  - 或在写入时做乐观锁、或者只缓存“最近窗口”的稳定段

### Q12. Redis TTL 会导致记忆丢失吗？你如何在产品/体验上解释？

**参考答案要点：**

- Redis 存储是带 `ex=ttl_seconds` 的：超过 TTL Redis 会自动过期。
- 体验解释：即便 Redis 丢了，也可以从 Postgres 回填（Hybrid 场景），但若只配置了 InMemory 或 Redis-only，则会在 TTL 到期后丢失上下文。
- 你可以说：你在 README 里说明了优先级与回退策略，保证不同部署都能“能用优先”，并让用户理解记忆保留的边界。

### Q13. `session_id` 设计上你怎么考虑安全与碰撞风险？

**参考答案要点：**

- 当前端点要求客户端传 `session_id`，并在后端当作 key 使用。
- 安全方面：
  - 你需要在面试里提：服务端不应信任客户端提供的 session_id 用于越权访问（若要严格权限，需要在认证/授权后绑定 session_id 与 user_id）
  - 碰撞方面：session_id 通过前端生成且格式约束（Pydantic `min/max_length`）可降低简单碰撞概率
- 强化建议：服务端可以在引入用户身份（auth）后把 key 变成 `user_id:session_id`，避免跨用户串话。

---

## 5. 工程化与可观测性

### Q14. 你能从日志/metrics 回答哪些线上问题？从哪里定位？

**参考答案要点：**

- 请求侧：`request_logging_middleware` 会记录 `request_id/method/path/status/duration_ms` 并注入 `X-Request-ID`。
- 工具侧：calculator/web_search 工具里有成功/失败日志（包含输入与耗时）。
- agent 侧：有 `logger.exception` 记录 stream failure，并在构建 memory store 时打印初始化策略。
- 定位路径：根据 `request_id` 在日志聚合系统里追踪一次请求经历了哪些阶段、工具是否成功、以及是否触发 fallback。

### Q15. 你如何给模型调用、web 搜索、数据库读写加超时/重试/熔断？

**参考答案要点：**

- 当前实现你可以如实说：stream fallback 用了 `asyncio.to_thread(agent.invoke, inputs)` 作为兜底。
- 加分点：你会如何做增强：
  - 模型调用/工具调用加超时（例如使用 async 客户端支持 timeout 或在调用层包裹）
  - web search 设置合理 max_results，并在失败时降级（返回无 sources 但不影响 answer）
  - 数据库连接池设置 timeout，并对读取失败做 retry（仅对可重试错误）
  - 熔断策略：对持续失败的依赖（搜索/外部服务）短时间内直接降级

### Q16. 你的错误处理策略是什么？哪些返回 400，哪些返回 500？

**参考答案要点：**

- `router` 在 `chat.py` 中区分 `ValueError` -> 400（例如缺少必要配置），其他异常 -> 500。
- 流式 endpoint：会 yield `error` 事件，并在 `finally` 结束。
- 可再补充你会怎么细化：对用户可修正错误（参数错误、会话标识无效）返回 400；对外部依赖失败（模型/搜索/数据库）返回 500 并可重试。

---

## 6. 测试与评估

### Q17. 你现在测试更偏接口契约，那你如何做“行为正确性”的验证？

**参考答案要点：**

- 当前单元/集成测试主要覆盖 API 契约与流式协议（包括 mock agent 返回结构）。
- 行为正确性建议：
  - 对 `calculator_tool` 做数学表达式的输入输出测试（可纯单元测试，不依赖模型）
  - 对 web search 工具用录制/回放（VCR）或 stub 数据测试 sources 解析
  - 对 agent 编排做“最小可控集成测试”：mock LLM 输出事件，验证 `tools_used/sources` 提取逻辑

### Q18. 如果要把系统提升到可评估（评测），你会引入什么指标/流程？

**参考答案要点：**

- 建议指标：
  - 工具调用命中率（需要工具的问题中模型实际调用了对应工具的比例）
  - 工具调用成功率与有效结果率（返回可解析 sources 的比例）
  - sources 覆盖率（有外部事实时是否给出来源）
  - 延迟（TTFT 首 token 延迟 + 端到端）
  - 降级成功率（外部依赖失败时仍能产出可用答案的比例）
- 流程：
  - 维护一份评测题集（计算/时效/跨领域）
  - 每次改动做离线回归 + 少量线上采样

---

## 7. 安全与合规（常见追问）

### Q19. 如何防范 prompt injection 导致工具被滥用？

**参考答案要点：**

- 你现在用 system_prompt 限制工具使用边界（计算必须 calculator，事实必须 web search）。
- 进一步增强思路：
  - 对工具参数做严格校验/白名单（长度、字符集、允许的查询范围）
  - 工具白名单：根据 skill/intent 动态允许的工具集合
  - 对可疑指令做过滤：例如当用户要求“泄露系统提示/密钥/内部结构”直接拒答

### Q20. API key/连接串/日志里是否会泄露敏感信息？你怎么做脱敏？

**参考答案要点：**

- 工具日志里尽量记录输入内容与耗时，但要避免输出包含密钥或敏感 headers。
- 建议做法：
  - 日志中对 `api_key/token/dsn` 做正则脱敏
  - 配置加载用环境变量，确保 `.env` 不提交到仓库（并且 CI/生产环境用安全注入）
  - 给日志系统设置最小权限与访问控制

---

## 你可以直接背的“总结句”（结尾模板）

你可以在每个回答最后加一句：

- “因此我在实现上把协议与解析做成了稳定的结构化输出，并通过测试/日志/兜底策略保证在依赖波动时仍可用。”

