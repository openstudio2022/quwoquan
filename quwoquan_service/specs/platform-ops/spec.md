# platform-ops（运维/平台域）

## Purpose

本规格冻结 `platform-ops` 的需求边界、门户定位、控制面接入规范与部署原则。

`platform-ops` 的目标不是建设传统专职 SRE 后台，而是建设**全栈研发自助平台**，统一支撑各垂直领域服务的：
- 可观测性（日志、指标、trace、SLO、告警、runbook）
- 系统配置（`sys.*`、Secrets、配置包、配置治理）
- 服务治理（超时、重试、熔断、限流、降级、健康检查、发布/回滚）
- CI/CD 与发布控制（门禁、灰度、回滚、变更审计）
- 环境与依赖治理（组网、路径、数据库、缓存、消息、弹性策略）

**重要边界**：
- `platform-ops` 负责**系统与实现层面能力**，不承载业务运营策略。
- `product-ops` 负责**业务策略与业务事件数据**，包括实验、审核、推荐运营、投诉与申诉。
- `platform-ops` 不对 App 暴露业务 API，只对研发自助门户与内部控制面开放。

本域的单一事实来源在 `contracts/`、`deploy/`、`runtime/` 与控制面元数据中；服务实现侧必须通过 `runtime/` 与 codegen 接入，禁止手写第二套控制面契约。

---

## Frozen Scope

### 统一 Web 门户中的 Platform Ops 板块

统一 Web 门户 `ops-portal` MUST 提供 `Platform Ops` 一级工作域，至少包含以下菜单：
- 服务目录
- 配置中心
- 治理策略
- 发布灰度
- 环境与依赖
- 可观测与 SLO
- Runbook 与演练
- CI/CD 门禁

### 统一管理的系统级能力

`platform-ops` MUST 管理：
- 服务目录与归属关系
- `sys.*` 系统配置项与配置包版本
- 高风险配置的灰度、回滚与审计
- 治理策略模板与服务级覆盖
- 发布状态、环境状态、依赖状态
- SLO / error budget / 告警模板

`platform-ops` MUST NOT 管理：
- `ops.*` 业务策略
- 内容审核、投诉、处罚、申诉
- 推荐召回/粗排/精排运营策略
- 面向用户的人群实验配置

---

## ADDED Requirements

### Requirement: 三类面必须可拆分

每个垂直领域 MUST 按以下三类面定义稳定边界：
- `user-plane`：面向 App / Gateway / Orchestrator 的用户流量面
- `platform-control-plane`：面向 `platform-ops` 的系统治理与配置管理面
- `product-control-plane`：面向 `product-ops` 的业务运营与治理管理面

三类面必须在**契约层独立**，不得把控制面动作混入用户面 API。

#### Scenario: 新领域服务接入

- **WHEN** 新增一个领域服务或给已有领域服务接入控制面
- **THEN** 必须同时识别三类面边界
- **AND** 控制面接口必须通过统一控制面元数据生成
- **AND** 不得以“先混在用户接口里、后续再拆”为前提推进

### Requirement: 三类面支持部署任意组合

三类面 MUST 支持部署时的任意组合，不得把部署拓扑固化进契约设计。

允许的部署形态包括：
- 单进程合并
- 同 Pod 双容器或三容器
- `seed-box` 控制面容器与领域处置服务同 Pod
- 控制面独立 Deployment / Pod
- `platform-control-plane` 与 `product-control-plane` 分别独立扩缩容

#### Scenario: 短期共享 Pod，长期独立 Pod

- **WHEN** 当前阶段为了降低运维复杂度，控制面通过 `seed-box` 容器与领域处置服务同 Pod 部署
- **THEN** 契约、鉴权、审计、健康检查与资源配置仍须按独立控制面设计
- **AND** 后续拆分为独立 Pod 时不得要求改写业务契约或大规模返工

### Requirement: 控制面契约统一元数据化

所有领域服务面向 `platform-ops` 的管理接口 MUST 由统一控制面元数据驱动，并支持 codegen 产出。

控制面元数据至少必须表达：
- plane 类型（`user-plane` / `platform-control-plane` / `product-control-plane`）
- route、operation、scope、危险级别、审计要求
- 配置项 schema（owner、type、default、scope、reload、rollout、risk_level）
- 部署能力（可同 Pod / 可独立 Deployment / 资源画像 / 拆分触发条件）

#### Scenario: 控制面接口新增

- **WHEN** 某领域新增一个运维管理操作，如配置变更、治理策略下发、发布回滚、依赖状态读取
- **THEN** 必须先更新控制面元数据
- **AND** 由 codegen 生成 Go handler scaffold、TS client/schema、Python client/schema
- **AND** 不允许在服务中直接手写一套临时 admin API

### Requirement: 系统配置与业务运营配置严格分层

系统 MUST 遵从 `contracts/configuration.md`：
- `sys.*` 属于 `platform-ops`
- `ops.*` 属于 `product-ops`
- IaC / K8s / HPA / 网络 / 证书等基础设施参数不进入业务配置中心

#### Scenario: 高风险运行时参数变更

- **WHEN** 调整 long-polling 周期、超时、重试、熔断、限流、采样率、批处理大小等运行时参数
- **THEN** 必须作为 `sys.*` 管理
- **AND** 必须具备配置包版本、灰度、回滚、审计与可观测标记

### Requirement: 统一服务治理约束（强制）

系统 MUST 统一遵从 `contracts/service_governance.md`，并通过 `runtime/` 公共库落地：
- 超时、重试、熔断、限流、降级可配置、可灰度、可回滚
- 健康检查与优雅关停（readiness/liveness/graceful shutdown）
- 幂等、分页、错误码与追踪 headers 一致

#### Scenario: 新服务接入（onboarding）

- **WHEN** 新增一个业务服务或新增一个关键接口
- **THEN** 必须先接入 `runtime/errors`、`runtime/observability`、`runtime/config`、`runtime/messaging`
- **AND** 面向 `platform-ops` 的控制面能力必须走统一控制面契约与代码生成

### Requirement: 可观测性统一落地（强制）

系统 MUST：
- 结构化日志字段对齐 `contracts/log_fields.md`
- 指标对齐 `contracts/metrics.md`
- trace/requestId/pageId 等对齐 `contracts/openapi/common.yaml` 与 `contracts/error_codes.md`
- 异步链路 envelope 对齐 `contracts/messages/envelope.schema.json`

平台模块 SHOULD 提供：
- Dashboard 模板、告警模板
- SLO 与 error budget 模板
- 发布与配置灰度的观测面板

### Requirement: 统一 Web 门户技术选型冻结

`ops-portal` 的前端技术选型冻结为：
- `React + TypeScript`
- 管理后台组件体系（表格、表单、审计、diff、工作台）

`platform-ops` 后端主栈冻结为：
- `Go`

该选型用于确保控制面与现有 `runtime/`、`deploy/`、codegen 工具链保持一致，避免引入第二套平台主栈。

