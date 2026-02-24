# platform-ops（运维/平台域）

## Purpose

本规格定义“运维/平台（SRE/Platform Ops）”域的统一交付物与约束，用于支撑所有服务的：
- 可观测性（日志/指标/trace、看板、告警、SLO）
- 系统配置（配置中心、Secrets、配置治理）
- 服务治理（超时/重试/熔断/限流/降级、健康检查、发布/回滚）
- 可靠性与性能基线（容量、压测口径、误差预算）

**重要边界**：
- `product-ops` 是**产品运营服务（业务域）**：策略/埋点/实验/访问记录等业务数据。
- `platform-ops` 是**运维/平台域**：系统与实现层面能力，不承载运营策略业务，不对 App 暴露业务 API。

本域的“单一事实来源”在 `contracts/` 与 `platform/`，服务实现侧必须通过 `runtime/` 统一复用。

---

## ADDED Requirements

### Requirement: 统一服务治理约束（强制）

系统 MUST 统一遵从 `contracts/service_governance.md`，并通过 `runtime/` 公共库落地：
- 超时/重试/熔断/限流/降级可配置、可灰度、可回滚
- 健康检查与优雅关停（readiness/liveness/graceful shutdown）
- 幂等、分页、错误码与追踪 headers 的一致性

#### Scenario: 新服务接入（onboarding）

- **WHEN** 新增一个业务服务（或新增一个关键接口）
- **THEN** 必须先接入公共库：`runtime/errors`、`runtime/observability`、`runtime/config`、`runtime/messaging`（按需 `runtime/experiments`、`runtime/learning`）
- **AND** 必须满足 `tasks.md` 的 “§0 全服务统一能力” 门槛

### Requirement: 可观测性（日志/指标/trace/告警）统一落地（强制）

系统 MUST：
- 结构化日志字段对齐 `contracts/log_fields.md`
- 指标对齐 `contracts/metrics.md`
- trace/requestId/pageId 等对齐 `contracts/openapi/common.yaml` 与 `contracts/error_codes.md`
- 异步链路 envelope 对齐 `contracts/messages/envelope.schema.json`

平台模块 SHOULD 提供：
- Dashboard 模板、告警模板（见 `platform/observability/`）
- SLO 口径与误差预算分解方法（见 `contracts/feedback_and_learning.md`）

### Requirement: 系统配置（运维配置）统一落地（强制）

系统 MUST：
- 配置分层与治理遵从 `contracts/configuration.md`
- 配置落地方式遵从 `platform/config/README.md`
- 运营配置（业务策略/实验/活动）不得进入系统配置中心，应由 `product-ops` 管理为业务数据

#### Scenario: 高风险配置变更

- **WHEN** 调整超时/重试/限流/降级/采样率等高风险配置
- **THEN** 必须具备审计、灰度、回滚能力，并能在日志/指标中标注生效版本或变更号

### Requirement: 体验指标与反馈闭环（平台视角）统一接入

系统 MUST 支持把端侧体验指标（RUM）与端云链路（trace/requestId）在检索层面关联；
推荐/助手等 AI 能力 MUST 具备“采集→评估→版本化→灰度→回滚”最小闭环（见 `contracts/feedback_and_learning.md`）。

