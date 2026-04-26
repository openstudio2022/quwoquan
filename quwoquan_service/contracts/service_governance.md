# 服务治理统一规范（Service Governance）

目标：把“可上线的工程质量”标准化，让每个服务只聚焦业务逻辑，公共的治理能力统一由 `runtime/` 落地，且与 `contracts/` 对齐。

本规范适用于：Gateway / Orchestrator / Content / Circle / User / Chat / Assistant / Ops（运营）。
本规范中“运营”服务统一称为 `product-ops`（见 `contracts/roles_and_scopes.md`）。

---

## 1. 必须遵从的 contracts（引用）

- 错误码：`contracts/error_codes.md`
- 可观测性字段/指标：`contracts/log_fields.md`、`contracts/metrics.md`
- Headers 与分页：`contracts/openapi/common.yaml`
- 异步 envelope：`contracts/messages/envelope.schema.json`
- 配置分层：`contracts/configuration.md`
- 体验指标与 SLO：`contracts/feedback_and_learning.md`

---

## 2. 统一运行时要求（必须）

### 2.1 超时、重试、熔断、降级（必须可配置）

- 所有下游调用 MUST 设置超时（无默认无限等待）。
- 重试 MUST 具备上限、退避、抖动，并避免对非幂等操作造成重复副作用。
- 熔断/隔离（circuit breaker / bulkhead）MUST 支持按下游维度配置与生效。
- 降级 MUST 有明确策略：返回“可渲染的降级数据”或返回明确错误码（并可通过配置开关快速启停）。

> 相关参数必须是“运维/系统配置”（`sys.*`），不得混入运营配置。

### 2.2 限流与保护（必须）

- Gateway MUST 支持 per-user/per-ip 限流与黑白名单。
- 业务服务 SHOULD 支持关键资源的自保护（热点保护、并发上限、队列化/排队）。
- 限流触发必须可观测：日志 + 指标 + 可告警。

### 2.3 健康检查与优雅关停（必须）

- MUST 提供 liveness/readiness（或等价）健康检查。
- MUST 支持优雅关停：停止接收新请求、完成 in-flight 请求、关闭连接池。
- Readiness MUST 反映关键依赖是否可用（或至少反映“服务是否可对外提供核心能力”）。

### 2.4 幂等与一致性（必须）

- create/ingest 类接口 MUST 支持 `Idempotency-Key`（见 `contracts/openapi/common.yaml`）。
- 异步消费 MUST 支持幂等（至少“可重复消费不产生重复副作用”）。
- 最终一致性场景 MUST 明确：写入、事件发布、读模型更新的时序与可接受延迟。

### 2.5 版本化与兼容性（必须）

- 外部 API 必须版本化：`/v1/...`（或等价）。
- Schema 演进 MUST 向后兼容（新增字段优先；删除/改义需版本切换）。
- 错误码 `MODULE.KIND.REASON` MUST 稳定，不随实现细节变化。

---

## 3. 统一可观测性要求（必须）

- HTTP/GRPC 请求 MUST 产出访问日志（含 durationMs、status、traceId、requestId、pageId）。
- 所有异常 MUST 产出错误日志（含 runtimeFailure.code/origin/kind/nature、location、context.attributes、recovery.action、disruptionLevel）。
- 核心指标 MUST 覆盖：请求量、错误率、延迟分布（p95/p99）、依赖失败、队列积压（如适用）。
- SLO 告警 MUST 以“用户旅程/关键接口”为主（避免只看 CPU/Mem）。

实现必须通过公共库：`runtime/observability` + `runtime/errors`。

---

## 4. 统一配置要求（必须）

- 配置来源分层（env/secrets/config-center/file/默认值）遵从 `platform/config/README.md`。
- 配置命名遵从 `contracts/configuration.md`（`sys.*` vs `ops.*`）。
- 高风险配置变更 MUST 审计、灰度、回滚，并能在日志中标注生效版本或变更号。

实现必须通过公共库：`runtime/config`。

---

## 5. 统一安全与隐私（必须）

- 日志/事件/指标不得泄露敏感信息（token、密码、验证码、隐私字段）。
- debugMessage 必须脱敏（见 `contracts/error_codes.md`）。
- Authorization 与身份上下文必须由网关统一注入与透传（见各服务 OpenAPI/common headers）。

---

## 6. 开发前仍需补齐的信息清单（用于进入“每服务详细开发”）

> 这些信息若缺失，会导致实现时各服务各自决策、难以统一。

### 6.1 统一认证与授权模型

- accessToken 的 claim：userId、activePersonaId（是否内置）、roles/scopes（是否需要）
- 服务间调用身份：SVC-to-SVC 的鉴权方式（mTLS/签名/内网凭据）

### 6.2 统一“规范化 endpoint 名”字典（用于 metrics/日志 label）

- 例如：`orch.discovery_feed.list`、`chat.message.list` 等
- 需与端侧 `pageId` 区分：pageId 是来源；endpoint 是接口名

### 6.3 统一 ID 生成与排序口径

- 全局 ID：是否使用 ULID/KSUID（便于按时间排序），或由存储层生成
- Cursor 分页：cursor 的编码方式、排序字段约定（createdAt/id 复合排序）
- 时间口径：统一时区（UTC）与时间戳格式（ISO8601/epoch）

### 6.3 数据保留与成本约束

- 体验事件/行为事件的保留期限、采样策略、聚合策略
- trace/log 的保留期限与采样策略

### 6.4 契约测试与兼容性策略

- OpenAPI 校验、示例响应、端云契约测试的基线流程
- 破坏性变更的发布流程（版本迁移、双写/双读策略）

### 6.5 统一依赖治理（DB/MQ/Cache）与降级策略

- 依赖不可用时的降级原则（读降级/写排队/异步补偿）
- Outbox/Inbox（或等价）模式是否采用，用于“写库 + 发事件”的一致性
- MQ 重试与死信策略（重试次数、延迟、人工介入流程）

### 6.6 统一隐私与合规边界

- 哪些字段允许进入日志/埋点/体验事件（脱敏规则）
- PII 的最小采集与访问控制策略（尤其是体验指标与行为事件）

