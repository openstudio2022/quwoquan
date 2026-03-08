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

## 产品模型

### 一级菜单
- `服务目录`
- `配置中心`
- `治理策略`
- `发布灰度`
- `环境与依赖`
- `可观测与 SLO`
- `Runbook 与演练`
- `CI/CD 门禁`

### 门户全局能力绑定

`platform-ops` 在统一门户中必须依附以下全局能力：
- 环境切换：`local / dev / integration / prod`
- 全局搜索：服务、配置项、发布单、依赖、告警、审计记录
- 全局通知：灰度中断、回滚完成、SLO burn、审批待处理、门禁失败
- 全局工作台：我负责的服务、待审批配置、待处理告警、待执行 runbook
- 全局审计入口：高风险配置、治理动作、发布动作、放行动作统一检索

### 菜单模型

| 一级菜单 | 目标 | 关键视图 |
|---|---|---|
| 服务目录 | 管理领域、服务、plane、owner、依赖与环境归属 | 服务清单、依赖拓扑、领域归属、环境映射 |
| 配置中心 | 管理 `sys.*` 配置项、配置包、环境差异与配置版本 | 配置项列表、配置包 diff、版本历史、回滚 |
| 治理策略 | 管理 timeout/retry/circuit/rate-limit/degrade/health 策略模板 | 策略模板、服务覆盖、危险变更确认 |
| 发布灰度 | 管理配置灰度、发布进度、回滚与阶段门禁 | rollout 面板、阶段检查、回滚动作 |
| 环境与依赖 | 管理组网、路径、数据库、缓存、消息、依赖健康与资源画像 | 环境矩阵、依赖状态、连接画像、弹性基线 |
| 可观测与 SLO | 管理日志、指标、trace、SLO、error budget、告警模板 | Dashboard、SLO、告警、预算消耗 |
| Runbook 与演练 | 管理故障处置手册、恢复流程与演练任务 | runbook 列表、演练计划、演练记录 |
| CI/CD 门禁 | 管理 build/test/gate/deploy 规则与发布阻断条件 | 门禁规则、失败记录、放行记录 |

### 核心对象模型

| 对象 | 说明 |
|---|---|
| `PortalWorkspace` | 门户工作区上下文，包含环境、服务、域、权限与全局筛选状态 |
| `ServiceCatalogEntry` | 服务目录项，描述领域、owner、三类面、依赖、环境归属 |
| `PlaneBinding` | 某领域三类面与进程/容器/Pod 的部署绑定关系 |
| `ConfigSchema` | 配置项 schema，描述 key、type、default、scope、reload、risk_level |
| `ConfigPackage` | 一次发布的配置包快照，含版本、环境、服务、变更摘要 |
| `ConfigRelease` | 配置发布记录，含阶段、灰度比例、观察窗口、回滚状态 |
| `GovernancePolicy` | 治理策略模板，覆盖 timeout/retry/circuit/rate-limit/degrade/health |
| `DependencyProfile` | 服务依赖画像，描述 DB/Redis/MQ/HTTP 下游与健康状态 |
| `EnvironmentTopology` | 环境级部署拓扑，描述 domain-plane 到 process 的映射 |
| `SLOPolicy` | SLO / error budget 定义与门禁规则 |
| `Runbook` | 运维处置手册与标准恢复步骤 |
| `GateRule` | CI/CD 门禁规则、阻断条件与审计记录 |
| `AuditRecord` | 所有高风险配置与治理动作的统一审计记录 |

### 领域接入矩阵

每个领域接入 `platform-control-plane` 时，必须至少声明以下对象与动作：

| 领域 | 最低对象集合 | 最低动作集合 |
|---|---|---|
| `content` | ServiceCatalogEntry / ConfigSchema / ConfigRelease / GovernancePolicy / DependencyProfile / SLOPolicy | 读配置、变更配置、治理策略下发、发布灰度、回滚、依赖状态读取 |
| `circle` | ServiceCatalogEntry / ConfigSchema / GovernancePolicy / DependencyProfile / AuditRecord | 读配置、治理策略下发、发布状态读取、回滚 |
| `chat` | ServiceCatalogEntry / ConfigSchema / GovernancePolicy / SLOPolicy / DependencyProfile | 读配置、轮询/超时参数治理、告警与 runbook 绑定 |
| `user` | ServiceCatalogEntry / ConfigSchema / GovernancePolicy / DependencyProfile / AuditRecord | 认证链路参数治理、发布灰度、回滚、依赖状态读取 |
| `assistant` | ServiceCatalogEntry / ConfigSchema / GovernancePolicy / SLOPolicy / DependencyProfile | 运行时参数、模型依赖健康、发布与回滚、观测与预算治理 |

约束：
- 上表是最低接入集，不是最终全量对象
- 任何领域如未声明 `platform-control-plane` 对象集合，视为未完成控制面接入
- 领域主对象的业务状态仍归各领域服务本身，不由 `platform-ops` 托管

## 元数据需求清单

`platform-ops` PRD 阶段冻结以下元数据对象需求，后续 `/design` 阶段细化字段级 schema：

### `control_plane.yaml`
用于定义每个领域的 `platform-control-plane` 契约：
- plane
- route
- operation
- scope
- danger_level
- audit_required
- rollout_capable
- deployment_profile

### `config_schema.yaml`
用于定义 `sys.*` 配置项：
- key
- owner
- description
- type
- default
- scope
- reload
- rollout
- risk_level
- secret

### `portal_menu.yaml`
用于定义门户 `Platform Ops` 菜单模型：
- 一级菜单
- 二级菜单
- 路由
- required_scope
- environment_aware

### `portal_shell.yaml`
用于定义 `platform-ops` 依赖的门户壳层能力：
- 全局环境切换
- 全局搜索域
- 全局通知类型
- 全局工作台视图
- 全局对象跳转入口

### `audit_schema.yaml`
用于统一高风险动作的审计事件：
- actor
- target
- action
- old_value / new_value
- environment
- version
- release_id
- approval_record

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

### Requirement: 门户菜单与对象模型必须可 codegen 消费

`platform-ops` 的菜单模型、对象模型与控制面能力必须能被统一 codegen 消费，避免门户、后端与脚本分别维护第二份模型。

#### Scenario: 新增一个 Platform Ops 菜单

- **WHEN** 新增一个一级或二级菜单，如新增“依赖容量画像”或“门禁放行历史”
- **THEN** 必须先更新 `portal_menu.yaml` 与关联对象模型
- **AND** 门户前端、Go client/schema、Python client/schema 必须消费同一份 metadata
- **AND** 不允许只在前端路由中临时手写菜单

### Requirement: 领域接入必须声明最低控制面对象集合

每个领域接入 `platform-control-plane` 时，必须至少声明最低对象集合与最低动作集合，以保证后续能够统一集成验收。

#### Scenario: 领域首次接入 Platform Ops

- **WHEN** 某领域第一次接入 `platform-ops`
- **THEN** 必须补齐该领域的服务目录、配置 schema、治理策略、依赖画像、发布与审计对象声明
- **AND** 必须通过元数据与 codegen 产出统一契约
- **AND** 不允许只开放零散只读接口作为“临时接入”

## 适用范围与约束

适用：
- 面向当前“全栈团队自助运维”的组织模式
- 适用于多领域服务、统一门户、统一控制面契约与统一 codegen 的平台建设
- 适用于短期同 Pod 共部署、长期独立 Deployment 的演进模式

约束：
- `platform-ops` 不是业务运营系统，不承接审核、实验、人群灰度、推荐运营
- `platform-ops` 不是 IaC 编排系统本体，只管理平台控制面可见的系统配置与发布治理
- `platform-control-plane` 契约必须独立于用户面 API，禁止为了部署方便混合接口

## `/design` 需要回答的方案比较

后续 `/design` 必须至少比较以下方案并给出选择理由：

1. 门户前端组织方式
- 单前端应用 + 域模块化
- 微前端

2. 控制面后端组织方式
- 单体 `platform-ops`
- 模块化单体 + 独立后台 worker
- 多服务拆分

3. 配置发布模型
- 配置包版本 + 渐进灰度
- 实时动态配置下发
- 混合模式

4. 部署映射模型
- 维持 `domain -> process`
- 升级为 `domain-plane -> process`

5. codegen 产物组织
- 统一控制面 codegen 子系统
- 扩展现有 `runtime-codegen` / `codegen_app_metadata`

## `/design` 前的任务拆解

- 明确 `platform-ops` 的门户信息架构与 RBAC 口径
- 明确 `ConfigSchema` / `ConfigPackage` / `ConfigRelease` / `GovernancePolicy` / `SLOPolicy` 的字段边界
- 明确 plane 级部署映射与 `seed-box` 演进策略
- 明确 `control_plane.yaml` 与 `config_schema.yaml` 的最小字段集
- 明确 `portal_shell.yaml` 与 `portal_menu.yaml` 的最小字段集
- 明确领域接入矩阵与最低控制面对象集合
- 明确 Web / Go / Python codegen 的目标路径与命名规范
- 明确配置灰度、回滚、审计、SLO 门禁与部署组合验证的验收闭环

