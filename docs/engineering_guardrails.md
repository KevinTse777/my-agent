# Engineering Guardrails（Epic A）

本文件定义项目的目录职责、依赖方向和代码边界，用于降低后续演进中的耦合与返工风险。

## 1. 目录职责

- `backend/app/routers`
  - 只处理 HTTP 入口：参数校验、调用 service、返回响应。
  - 不包含业务编排逻辑，不直接访问数据库或外部工具。
- `backend/app/services`
  - 业务与 Agent 编排层。
  - 负责流程、策略、异常归一、跨组件组合。
- `backend/app/tools`
  - 外部能力封装层（计算、搜索、第三方 API）。
  - 提供稳定输入输出，内置超时/重试/失败语义。
- `backend/app/core`
  - 横切基础设施：配置、日志、全局中间件、错误模型。
- `backend/app/schemas`
  - 接口请求/响应模型，不包含业务逻辑。
- `backend/app/tests`
  - 单测与集成测试，覆盖关键路径和异常路径。
- `frontend/src`
  - UI 与交互逻辑，不持有后端业务规则。

## 2. 依赖方向（必须遵守）

后端允许依赖方向：

`routers -> services -> tools/core`

补充规则：
- `routers` 可依赖 `schemas`、`services`、`core`
- `services` 可依赖 `tools`、`core`、`schemas`
- `tools` 只能依赖 `core` 与第三方 SDK
- `tools` 禁止依赖 `routers`
- `schemas` 不依赖 `services/tools`

## 3. 变更边界

- 新功能默认优先在 `services` 扩展，不在 `routers` 堆业务逻辑。
- 新外部集成默认通过 `tools` 增加，不在 `services` 直接发 HTTP。
- 超过 500 行有效改动的 PR 应拆分为多个可独立回滚的 PR。

## 4. 代码质量门槛

- 新增核心功能必须附带测试（单测或集成测试）。
- 关键路径代码必须有结构化日志字段（`request_id`、`session_id` 或 `task_id`）。
- 高风险变更（模型调用链、会话存储、响应结构）必须包含回滚说明。

## 5. Epic A 完成判定

- 有统一职责文档（本文件）。
- 团队代码评审以本文件作为依赖边界依据。
- 新增代码可被清晰归类，且未出现反向依赖。
