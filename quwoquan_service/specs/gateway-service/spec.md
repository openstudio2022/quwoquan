# gateway-service

## Purpose

云侧 API Gateway：端侧唯一入口，负责 HTTPS 终端、认证、限流、路由转发、统一可观测性与请求上下文透传。

---

## ADDED Requirements

### Requirement: HTTPS 终端与路由

系统 MUST 在网关层完成 HTTPS 终端与路由转发，端侧仅访问 Gateway，不直接访问业务服务。

#### Scenario: 按路径路由到编排或业务服务

- **WHEN** 客户端请求 `/v1/orch/...`
- **THEN** 网关将请求转发至 Orchestrator

- **WHEN** 客户端请求 `/v1/content/...`、`/v1/circles/...`、`/v1/user/...`、`/v1/chat/...`、`/v1/assistant/...`、`/v1/ops/...`
- **THEN** 网关将请求转发至对应业务服务

### Requirement: 认证与身份上下文

系统 MUST 在网关层校验 accessToken，并将 userId（及可选 personaId）注入到下游请求上下文中。

#### Scenario: 注入用户身份

- **WHEN** 客户端携带 Authorization: Bearer <token>
- **THEN** 网关解析并校验 token，将 userId 注入下游（header 或 internal context）

#### Scenario: 分身上下文透传（可选）

- **WHEN** 客户端携带 `X-Persona-Id`（或 token claim 含 activePersonaId）
- **THEN** 网关将 personaId 透传至下游服务，用于内容发布、互动、聊天等身份上下文

### Requirement: 幂等、追踪与可观测性

系统 MUST 支持请求幂等与全链路追踪，便于端云联调与故障排查。

#### Scenario: Idempotency-Key 透传

- **WHEN** 客户端请求携带 `Idempotency-Key`
- **THEN** 网关将该 key 透传至下游，确保 create/ingest 等接口可实现幂等

#### Scenario: requestId / traceId 注入

- **WHEN** 客户端未携带 requestId/traceId
- **THEN** 网关生成并注入，保证可通过 runId / requestId 关联 Ops 日志与 Assistant run

### Requirement: 限流与基础防护

系统 MUST 在网关层对用户与 IP 进行限流，并支持基础黑白名单策略（可由 Ops 下发）。

#### Scenario: 触发限流

- **WHEN** 单用户或单 IP 请求频率超过阈值
- **THEN** 网关返回 429 并记录到 Ops 事件/日志

