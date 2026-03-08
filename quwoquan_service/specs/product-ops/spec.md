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

