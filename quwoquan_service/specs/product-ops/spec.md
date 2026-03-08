# product-ops（产品运营域）

## Purpose

本规格冻结 `product-ops` 的需求边界、门户定位、控制面接入规范与运营闭环。

云侧 `product-ops` 是统一产品运营控制面，负责：
- 事件采集、指标分析、标签与分群
- 实验、分桶、灰度、回滚
- 推荐运营（召回、粗排、精排的受控干预）
- 内容治理（审核、投诉、下架、处置）
- 账号治理（处罚、申诉、恢复、客服工作流、证据、SLA、双签）
- 业务策略与业务配置（`ops.*`）

与平台运维域的边界：
- **product-ops**：业务策略与业务事件数据，可按用户/人群灰度、可审计、可回滚
- **platform-ops**：可观测性、系统配置、服务治理、可靠性/性能基线

> 说明：接口路径继续兼容 `/v1/ops/...`；本规格冻结的是“控制面产品边界与元数据驱动方式”，不是已有路径的重命名。

---

## Frozen Scope

### 统一 Web 门户中的 Product Ops 板块

统一 Web 门户 `ops-portal` MUST 提供 `Product Ops` 一级工作域，至少包含以下菜单：
- 事件与指标
- 标签与分群
- 实验与灰度
- 推荐运营
- 内容治理
- 账号治理
- 申诉与恢复
- 客服工单
- 策略中心

### 一个产品，两大模块

`product-ops` 第一阶段 MUST 作为一个统一产品交付，但内部边界必须清晰区分两大模块：
- `治理处置`：审核、投诉、处罚、申诉、恢复、客服、证据、SLA、双签
- `增长与推荐运营`：事件、指标、标签、实验、活动、推荐干预、优化闭环

`product-ops` MUST NOT 管理：
- `sys.*` 系统配置
- 超时、重试、熔断、限流、采样率等运行时参数
- K8s、HPA、组网、证书、DB 连接等基础设施配置

---

## ADDED Requirements

### Requirement: 三类面必须可拆分

每个垂直领域 MUST 按以下三类面定义稳定边界：
- `user-plane`
- `platform-control-plane`
- `product-control-plane`

`product-ops` 通过 `product-control-plane` 接入各领域，禁止绕过控制面契约直接侵入用户面 API。

#### Scenario: 领域治理动作接入

- **WHEN** 某领域需要支持审核、下架、处罚、申诉、推荐运营或运营统计读取
- **THEN** 必须通过 `product-control-plane` 契约暴露能力
- **AND** 不得把治理动作混入面向 App 的用户接口

### Requirement: 三类面支持部署任意组合

三类面 MUST 支持部署时任意组合：
- 可同进程
- 可同 Pod 不同容器
- 可通过 `seed-box` 容器承载控制面
- 可独立 Deployment / Pod

#### Scenario: 用户面高弹性，控制面稳态独立

- **WHEN** 用户流量增长，用户面需要更大规模弹性，而控制面以工作流、审计、批处理为主
- **THEN** 必须能够把 `user-plane` 独立扩缩容
- **AND** `product-control-plane` 维持独立的资源与副本策略
- **AND** 不得因为拆 Pod 而改动业务治理契约

### Requirement: 统一控制面契约元数据化

所有领域服务面向 `product-ops` 的管理接口 MUST 由统一控制面元数据驱动，并支持 codegen 产出。

控制面元数据至少必须表达：
- plane、route、operation、scope、审计要求
- 工作流状态机与危险动作确认
- 证据附件、SLA、双签审批要求
- 策略项 schema 与灰度范围
- 推荐干预项的作用层级（召回 / 粗排 / 精排 / 重排）

#### Scenario: 新增治理动作或策略项

- **WHEN** 某领域新增审核动作、处罚动作、申诉动作、实验策略或推荐运营策略
- **THEN** 必须先更新控制面元数据
- **AND** 由 codegen 生成 Go handler scaffold、TS client/schema、Python client/schema、App DTO
- **AND** 不允许直接手写临时运营后台接口

### Requirement: 埋点接收与事件治理

系统 MUST 提供统一埋点接收接口，支持：
- `page_access`
- `agent`
- `content_behavior`
- `circle_behavior`
- 后续可扩展业务事件

事件 schema MUST 统一，且可关联 `request/trace/page/session/user/device/experiment`。

#### Scenario: 内容行为埋点

- **WHEN** 客户端请求 `POST /v1/ops/events` 携带 `type=content_behavior`
- **THEN** 系统落库并产出可供推荐、分析、审核与运营归因消费的数据

### Requirement: 实验、分桶与业务灰度

系统 MUST 提供实验配置、分桶查询、放量、回滚与审计能力。

业务灰度 MUST 面向：
- 用户
- 人群
- 地域
- 渠道
- 实验层

#### Scenario: 实验分桶

- **WHEN** 客户端或服务请求 `GET /v1/ops/experiments/{experimentId}/bucket`
- **THEN** 系统返回稳定可复现、可审计、可关联 trace 的分桶结果

### Requirement: 推荐运营必须覆盖召回 / 粗排 / 精排

`product-ops` MUST 支持推荐运营受控干预，至少覆盖：
- 召回层：白名单、黑名单、活动池、保底池、领域开关、人群定向
- 粗排层：质量阈值、探索比例、新内容保护、风险内容预过滤
- 精排/重排层：模型版本、重排开关、多样性、去重、扶持因子、负反馈抑制

#### Scenario: 运营调整推荐策略

- **WHEN** 运营需要对推荐策略做灰度干预
- **THEN** 只能在受限参数空间内调整
- **AND** 必须具备版本、审计、灰度、回滚
- **AND** 不得以配置形式替代算法代码主逻辑

### Requirement: 内容治理与账号治理工作流

系统 MUST 提供统一治理工作流，覆盖：
- 举报
- 审核
- 下架
- 处罚
- 申诉
- 恢复

账号恢复 MUST 支持：
- 客服工作流
- 证据上传
- SLA
- 人工复核双签

#### Scenario: 账号恢复

- **WHEN** 用户发起账号恢复或申诉
- **THEN** 系统创建独立 case
- **AND** 证据、处理记录、SLA、审批人与双签记录必须完整可审计

### Requirement: 信息架构与业务体验配置

端侧一级 tab、二级 tab、栏目、版面、布局与体验类 feature flag 可以配置，但必须归属 `ops.*` 业务配置并由 `product-ops` 管理。

该类配置 MUST：
- 与 `ui_config.yaml` / app route metadata 对齐
- 支持按实验、人群、版本灰度
- 不得混入 `sys.*` 运行时参数

#### Scenario: 首页信息架构调整

- **WHEN** 运营调整首页一级/二级栏目顺序、布局或卡片样式
- **THEN** 必须通过元数据与业务配置生效
- **AND** 端侧、Go、Python 与 Web 的消费契约保持一致

### Requirement: 统一 Web 门户技术选型冻结

`ops-portal` 的前端技术选型冻结为：
- `React + TypeScript`

`product-ops` 后端主栈冻结为：
- `Go`

推荐训练、评估、离线分析等计算型能力保留：
- `Python`

---

## 核心对象模型

### 一、治理处置域对象

#### 1. `ModerationCase`
- 用途：统一承载举报、审核、下架、处罚、申诉、恢复等治理工单
- 关键字段：
  - `caseId`
  - `caseType`：report / moderation / enforcement / appeal / recovery
  - `targetType`：content / comment / circle / user / message / assistant_run
  - `targetId`
  - `status`
  - `priority`
  - `riskLevel`
  - `source`
  - `ownerId`
  - `slaPolicyId`
  - `createdAt` / `updatedAt`

#### 2. `EnforcementAction`
- 用途：记录已执行或待执行的治理动作
- 关键字段：
  - `actionId`
  - `caseId`
  - `actionType`：takedown / restrict / mute / suspend / ban / recover
  - `scope`
  - `reasonCode`
  - `effectiveAt` / `expireAt`
  - `executorId`
  - `approvalMode`：single / dual
  - `status`

#### 3. `AppealCase`
- 用途：承载用户申诉
- 关键字段：
  - `appealId`
  - `sourceCaseId`
  - `appellantId`
  - `appealReason`
  - `submittedEvidenceIds`
  - `status`
  - `reviewResult`

#### 4. `RecoveryCase`
- 用途：账号恢复与客服协作
- 关键字段：
  - `recoveryId`
  - `userId`
  - `originActionId`
  - `customerServiceTicketId`
  - `status`
  - `slaDeadlineAt`
  - `dualApprovalRequired`
  - `finalDecision`

#### 5. `EvidenceAsset`
- 用途：承载截图、录屏、聊天证据、补充材料
- 关键字段：
  - `evidenceId`
  - `caseId`
  - `assetType`
  - `storageUrl`
  - `hash`
  - `uploadedBy`
  - `uploadedAt`

#### 6. `ReviewDecision`
- 用途：保存审核、复核、双签记录
- 关键字段：
  - `decisionId`
  - `caseId`
  - `reviewerId`
  - `decision`
  - `reasonCode`
  - `comment`
  - `decisionAt`

### 二、增长 / 实验 / 推荐运营域对象

#### 1. `EventDefinition`
- 用途：定义统一事件 schema 与版本
- 关键字段：
  - `eventType`
  - `version`
  - `requiredFields`
  - `dimensions`
  - `owner`

#### 2. `MetricDefinition`
- 用途：统一指标口径
- 关键字段：
  - `metricId`
  - `category`
  - `formula`
  - `dimensions`
  - `guardrails`

#### 3. `Segment`
- 用途：标签与分群
- 关键字段：
  - `segmentId`
  - `populationRule`
  - `includedTags`
  - `excludedTags`
  - `estimatedSize`

#### 4. `Experiment`
- 用途：实验、放量、回滚与审计
- 关键字段：
  - `experimentId`
  - `layer`
  - `variants`
  - `targetSegments`
  - `rolloutPlan`
  - `status`
  - `guardMetrics`

#### 5. `RecommendationPolicy`
- 用途：统一推荐运营策略定义
- 关键字段：
  - `policyId`
  - `scenario`
  - `layer`：recall / prerank / rank / rerank
  - `policyType`
  - `targetSegments`
  - `status`
  - `version`

#### 6. `RecommendationOverride`
- 用途：受控干预召回、粗排、精排/重排
- 关键字段：
  - `overrideId`
  - `policyId`
  - `overrideScope`
  - `parameterSpace`
  - `effectiveWindow`
  - `rolloutMode`
  - `rollbackToken`

#### 7. `OptimizationRun`
- 用途：承载优化评估闭环
- 关键字段：
  - `runId`
  - `baselineVersion`
  - `candidateVersion`
  - `evaluationMetrics`
  - `decision`
  - `releasedAt`

---

## 工作流模型

### 一、治理处置工作流

#### 1. 举报 / 审核 / 处罚主链路
`reported -> triaged -> reviewing -> action_pending -> action_applied -> closed`

扩展路径：
- `reported -> dismissed`
- `reviewing -> escalated`
- `action_pending -> dual_approval_pending -> action_applied`

#### 2. 申诉工作流
`submitted -> evidence_pending -> under_review -> approved|rejected -> closed`

#### 3. 账号恢复工作流
`requested -> customer_service_intake -> evidence_verified -> dual_review -> recovered|rejected -> closed`

### 二、实验与推荐运营工作流

#### 1. 实验工作流
`draft -> review_pending -> running -> ramping -> completed|rolled_back -> archived`

#### 2. 推荐策略工作流
`draft -> simulated -> review_pending -> canary -> active -> rolled_back|retired`

#### 3. 推荐优化工作流
`hypothesis -> candidate_config -> offline_eval -> online_canary -> full_release|rollback`

---

## 推荐运营模型

### 召回层
- 白名单 / 黑名单
- 活动池 / 保底池
- 领域开关
- 人群定向召回
- 作者 / 圈子 / 内容扶持

### 粗排层
- 质量阈值
- 探索比例
- 新内容冷启动保护
- 风险内容预过滤
- 基础权重调节

### 精排 / 重排层
- 模型版本选择
- 多样性约束
- 去重策略
- 扶持因子
- 负反馈抑制
- rerank 开关

### 强约束
- 运营只能在受限参数空间内干预
- 干预必须版本化、可审计、可灰度、可回滚
- 干预不替代算法代码主逻辑

---

## 治理模型

### 内容治理
- 举报受理
- 审核判定
- 下架 / 恢复
- 风险升级
- 证据归档

### 账号治理
- 限制 / 禁用 / 封禁
- 申诉
- 恢复
- 客服协同
- SLA 跟踪
- 双签审批

### 权限与审计
- 高风险动作默认要求审计
- 账号恢复、永久处罚等动作要求双签
- 每个治理与推荐动作都必须产出审计记录与回滚上下文

---

## 后续 `/design` 需要比较的方案

### 方案组 1：产品形态
- 方案 A：一个统一产品，内部两大模块
- 方案 B：治理后台与增长后台拆成两个独立产品
- 当前选择：方案 A

### 方案组 2：控制面接入方式
- 方案 A：各领域手写运营接口
- 方案 B：统一 `product-control-plane` 元数据驱动 + codegen
- 当前选择：方案 B

### 方案组 3：推荐运营深度
- 方案 A：只做 AB 与指标
- 方案 B：覆盖召回 / 粗排 / 精排的受控干预
- 当前选择：方案 B

### 方案组 4：账号恢复
- 方案 A：简单状态回退
- 方案 B：正式 case/workflow + 证据 + SLA + 双签
- 当前选择：方案 B

