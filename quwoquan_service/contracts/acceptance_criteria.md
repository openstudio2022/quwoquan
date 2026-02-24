# 统一验收标准与测试驱动开发规范（TDD / Acceptance Criteria）

目标：让每个服务团队只聚焦业务实现，验收口径一致、过程可控、质量可持续提升。
本规范定义“每个开发任务/需求”必须提供的验收标准、测试要求与质量门禁（quality gates）。

---

## 1. 为什么需要（必要性）

必要。原因：
- **防止规格漂移**：把“做完了”从主观变成可验证的客观标准。
- **降低联调返工**：先写验收与测试（契约/集成），实现自然对齐 contracts。
- **让 SLO 可落地**：每个关键接口/旅程都能对应指标与告警。

---

## 2. 每个任务必须包含的验收标准（模板）

> 任务可以是：新增接口、改动 schema、加入一个推荐策略、增加一个体验埋点、优化性能等。
> 验收标准分为 7 类，缺一不可（允许某些类写 “N/A + 理由”）。

### 2.1 功能正确性（Functional）

- 覆盖的业务对象与动作（list/create/update/delete/ingest…）
- 关键场景 Given/When/Then（至少 3 条：正常、边界、错误）
- 兼容性：是否向后兼容（新增字段/默认值/弃用策略）

### 2.2 契约一致性（Contract）

- OpenAPI（或等价契约）已更新
- 响应结构遵从 `items/nextCursor`、错误响应遵从 `ErrorResponse`
- headers：`traceId/requestId/pageId/personaId` 等遵从 `contracts/openapi/common.yaml`

### 2.3 可观测性（Observability）

- 日志字段对齐 `contracts/log_fields.md`（至少能用 traceId/requestId/endpoint 关联）
- 指标对齐 `contracts/metrics.md`（至少 request_total + latency 分布 + errors_total）
- 关键失败/降级路径可被告警捕获（见 §2.6）

### 2.4 可靠性与性能（Reliability / Performance）

- 下游超时/重试/熔断/降级策略明确，且参数可通过 `sys.*` 配置
- 对应旅程/接口的 SLO 明确（参考 `contracts/feedback_and_learning.md`）
- 若为 P0 接口：必须给出 p95/p99 目标与误差预算归因口径

### 2.5 配置与发布（Config / Rollout）

- 运维/系统配置（`sys.*`）与运营配置（`ops.*`）边界明确（见 `contracts/configuration.md`）
- 变更可灰度、可回滚，并能在日志/指标中标注版本/变更号

### 2.6 告警与 SLO 门禁（Alerting / SLO）

- 为关键旅程/关键接口提供告警规则（错误率、尾延迟、依赖失败、队列积压等）
- 明确：触发阈值、告警级别、处理手册入口（Runbook 可后补，但必须留占位）

### 2.7 安全与隐私（Security / Privacy）

- 不记录敏感信息（token/密码/验证码/PII），debugMessage 脱敏（见 `contracts/error_codes.md`）
- 权限/鉴权路径明确（见 `contracts/authn_authz.md`）

---

## 3. 测试要求（TDD：先写验收与测试，再写实现）

### 3.1 必须具备的测试层（按任务选择）

- **单元测试**（必需）：核心业务逻辑、边界条件、错误码映射
- **契约测试**（必需）：OpenAPI 校验 + 示例请求/响应（golden file 或 schema 校验）
- **集成测试**（建议，P0 必需）：Docker Compose 依赖（MongoDB/PG/Redis/MQ）+ 真实调用链
- **端到端/预发验证**（P0 必需）：至少走一条关键旅程（可用脚本/回放）

### 3.2 质量门禁（Quality Gates，合并前必须通过）

- contracts 更新且通过校验（OpenAPI/Schema）
- lint/format/静态检查通过
- 单测通过（含覆盖核心路径）
- P0 接口：基准性能验证（至少本地压测/对比）+ SLO 告警可用

### 3.3 自动化与合规门禁（Commercial-grade）

- CI 必须自动执行并阻断：secret scan、依赖漏洞扫描（SCA）、基础 SAST（高危）
- CD 必须支持：自动部署到环境 + 一键回滚 + 发布审计（版本/时间/操作者）
- 隐私与安全：字段分级标注齐全；开启匿名化时日志输出符合预期；禁止 SECRET 泄露（见 `contracts/privacy_and_security.md`）

---

## 4. 与公共库的关系（强制复用）

验收中涉及的横切能力必须通过 `runtime/` 落地，不允许各服务自行实现一套：
- `runtime/errors`、`runtime/observability`、`runtime/config`、`runtime/messaging`、`runtime/experiments`、`runtime/learning`

