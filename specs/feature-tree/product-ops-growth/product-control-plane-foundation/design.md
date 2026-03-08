# Design：product-control-plane-foundation

## 设计动因

现有 `product-ops-growth` L1 已覆盖事件、实验、反馈优化等能力线，但尚缺一个共同上位节点来统一：
- `product-ops` 作为“一个产品，两大模块”的产品形态
- 各领域 `product-control-plane` 的统一接口约束
- 审核 / 处罚 / 申诉 / 恢复的工作流上位模型
- 推荐运营在召回 / 粗排 / 精排 / 重排层的统一干预边界
- `ops.*` 与端侧 IA / 体验配置的关系

没有这层共同基线，后续很容易出现：
- 事件、实验、治理、推荐运营各自建模
- 各领域手写各自的运营后台接口
- 审核与恢复没有统一 case/workflow
- 推荐运营只剩 AB 分桶，无法覆盖召回与排序策略
- 审计、证据、双签、SLA 分散在不同流程中，难以统一收口

## 上游评审结论

当前 `spec.md` 已足以支撑 `/prd` 阶段冻结产品边界与对象模型。进入 `/design` 后，本节点必须把“方向性产品定义”推进为“实施前设计基线”，重点细化：
- 元数据字段级 schema
- 工作流状态机与危险动作确认模型
- 推荐运营参数空间与 guardrail
- 审计模型、权限模型与附件模型
- 各领域 `product-control-plane` 接入模板

本次 `/design` 的目标就是完成上述设计基线，使后续 `/dev` 可以直接按 metadata-first 推进。

## 方案比较

### 方案 A：拆成两个独立产品
- 产品 1：治理处置后台
- 产品 2：增长 / 实验 / 推荐后台

优点：
- 各自垂直聚焦
- 权限与导航更清晰

缺点：
- 壳层、权限、审计、搜索、通知重复
- Case / 策略 / 指标容易分裂成两套体系
- 不符合当前“全栈共担、先少角色拆分”的组织形态

### 方案 B：一个产品、两大模块

优点：
- 门户壳层统一
- 权限、审计、工单、证据、搜索可复用
- 更适合当前团队规模和共担模式

缺点：
- 产品内部信息架构与权限设计要求更高

结论：
- 选择方案 B。

### 方案 C：只做实验/指标平台，不纳入治理处置

优点：
- 初期实现范围更小
- 更容易只落 AB 与埋点闭环

缺点：
- 治理处置继续散落在各领域
- 申诉、恢复、客服、证据、双签无法复用统一模型
- 推荐运营与治理动作无法共享审计和工作台

结论：
- 不选。与“统一运营控制面”的目标冲突。

### 方案 D：各领域手写运营管理接口

优点：
- 短期看起来更快
- 不需要先定义统一元数据

缺点：
- 各领域接口命名、鉴权、审计、危险动作口径不一致
- Web / Go / Python / App 无法共用契约
- 后续返工成本高，且与 metadata-first 相悖

结论：
- 不选。必须采用统一 `product-control-plane` 元数据驱动 + codegen。

## 关键决策

### 1. 产品形态
- `product-ops` 第一阶段作为一个统一产品交付
- 内部保留两大模块边界：
  - `治理处置`
  - `增长 / 实验 / 推荐运营`

### 2. 控制面接入方式
- 各领域通过统一 `product-control-plane` 接入
- 控制面接口一律由元数据驱动，不允许手写第二套临时后台 API

### 3. 元数据对象
本节点冻结以下共同对象：
- `control_plane.yaml`
- `workflow.yaml`
- `audit_schema.yaml`
- `config_schema.yaml`

### 4. 推荐运营深度
- 不止做 AB 分桶
- 必须覆盖召回、粗排、精排 / 重排的受控干预
- 干预只允许在受限参数空间内发生

### 5. 账号恢复模型
- 不采用“直接改状态”的轻量方案
- 采用正式 `case + workflow + evidence + SLA + dual-approval` 模型

### 6. 端侧 IA 与体验配置
- 一级 / 二级 tab、栏目、版面、布局、体验 feature flag 归入 `ops.*`
- 按用户 / 人群 / 实验灰度
- 不得和 `sys.*` 的 long-polling、超时、限流、采样率混用

### 7. 部署策略
- 逻辑上：`product-control-plane` 独立
- 部署上：短期允许 `seed-box` 同 Pod，共享部署
- 长期：独立 Deployment / Pod 与独立扩缩容

## 统一产品信息架构

### 顶层导航

统一门户中的 `Product Ops` 工作域固定以下信息架构：

| 一级分组 | 二级模块 | 主要对象 |
|---|---|---|
| 增长与分析 | 事件与指标 | `EventDefinition`、`MetricDefinition` |
| 增长与分析 | 标签与分群 | `Segment`、`TagRule` |
| 增长与分析 | 实验与灰度 | `Experiment`、`ExperimentAssignment` |
| 增长与分析 | 推荐运营 | `RecommendationPolicy`、`RecommendationOverride` |
| 治理处置 | 内容治理 | `ModerationCase`、`ReviewDecision` |
| 治理处置 | 账号治理 | `EnforcementAction`、`RecoveryCase` |
| 治理处置 | 申诉与恢复 | `AppealCase`、`RecoveryCase` |
| 治理处置 | 客服工单 | `ModerationCase`、`EvidenceAsset` |
| 公共配置 | 策略中心 | `ops.*` 配置项与策略模板 |

### 全局工作台

`product-ops` 在统一门户中必须具备以下工作台视图：
- 我发起的 case / 实验 / 策略变更
- 待我审批的双签动作
- 超 SLA 的治理与恢复 case
- 正在灰度中的实验与推荐策略
- 需要补证据或补信息的 case

## 业务对象与领域接入设计

### 设计原则

- 各领域保持主状态真相源
- `product-ops` 只维护治理、运营、分析、工作流与审计对象
- `product-control-plane` 提供的是“对象视图 + 受控动作”，不是“复制一份业务聚合”

### 领域接入矩阵

| 领域 | 主业务对象 | 接入 `product-control-plane` 的对象视图 | 允许的关键动作 |
|---|---|---|---|
| `content` | post / comment / media / report | 内容对象、举报对象、审核对象、推荐对象 | 举报、下架、恢复、精选、扶持、策略读取 |
| `circle` | circle / member / file / feed | 圈子对象、成员治理对象、推荐对象 | 圈子治理、成员处置、精选、扶持、策略读取 |
| `chat` | conversation / message / member | 会话审计对象、敏感治理对象、投诉对象 | 审计读取、敏感处置、投诉处理 |
| `user` | profile / auth / persona / setting | 账号治理对象、申诉对象、恢复对象 | 限制、禁用、恢复、申诉处理、客服协同 |
| `assistant` | run / event / scorecard / consent | 运行治理对象、学习反馈对象、策略对象 | 审核、策略调整、实验接入、反馈归因 |

### 控制面对象分层

| 对象层 | 说明 | 示例 |
|---|---|---|
| `BusinessSnapshot` | 来自领域服务的只读快照 | 内容摘要、用户状态、圈子状态 |
| `GovernanceCase` | 治理工单对象 | `ModerationCase`、`AppealCase`、`RecoveryCase` |
| `PolicyObject` | 策略与配置对象 | `RecommendationPolicy`、`ops.*` 配置项 |
| `AuditObject` | 审计与时间线对象 | `AuditEvent`、`ReviewDecision` |
| `EvidenceObject` | 证据与附件对象 | `EvidenceAsset` |

### 与现有对象的映射

- `content/report/service.yaml` 已经证明“举报对象在领域侧存在，处理动作面向运营可见”
- `ops/experiment_bucket/service.yaml` 已经证明“实验分桶对象在运营域存在，并可供 app / runtime 消费”

结论：
- 设计上不需要从零发明对象边界，而是将现有 `report`、`experiment_bucket`、`visit_record` 等对象上升到统一产品模型之下

## 元数据方案

### 1. `control_plane.yaml`

用于表达“各领域如何以 `product-control-plane` 暴露对象和动作”。

建议最小结构：

```yaml
plane: product-control-plane
domain: content
object_types:
  - object_type: moderation_case
    source_entity: Report
    view_model: ModerationCase
    routes:
      - method: GET
        path: /v1/control-plane/content/moderation/cases/{caseId}
        operation: GetModerationCase
        scopes: [ops.case.read]
      - method: POST
        path: /v1/control-plane/content/moderation/cases/{caseId}:applyAction
        operation: ApplyEnforcementAction
        scopes: [ops.case.write]
        danger_level: high
        approval_mode: dual
```

关键字段：
- `plane`
- `domain`
- `object_type`
- `source_entity`
- `view_model`
- `routes`
- `scopes`
- `danger_level`
- `approval_mode`
- `deployment_profile`

### 2. `workflow.yaml`

用于表达治理处置和恢复的状态机。

建议最小结构：

```yaml
workflow_id: recovery_case_v1
object_type: RecoveryCase
states:
  - requested
  - customer_service_intake
  - evidence_verified
  - dual_review
  - recovered
  - rejected
transitions:
  - from: requested
    to: [customer_service_intake, rejected]
  - from: customer_service_intake
    to: [evidence_verified, rejected]
approval_requirements:
  dual_review:
    approvers: 2
    distinct_roles: true
sla_policy:
  target_hours: 24
```

关键字段：
- `workflow_id`
- `object_type`
- `states`
- `transitions`
- `approval_requirements`
- `sla_policy`
- `evidence_requirements`

### 3. `audit_schema.yaml`

用于统一所有高风险治理和策略动作的审计结构。

关键字段：
- `audit_id`
- `actor`
- `environment`
- `domain`
- `object_ref`
- `action`
- `before`
- `after`
- `workflow_ref`
- `evidence_refs`
- `request_id`
- `trace_id`
- `rollback_token`

### 4. `config_schema.yaml`

用于表达 `ops.*` 业务配置。

重点支持：
- 推荐策略参数
- IA / tab / 布局 / feature flag
- 审核策略参数
- 实验与放量参数

示例命名：
- `ops.reco.discovery.recall.whitelist_enabled`
- `ops.reco.discovery.prerank.new_content_boost`
- `ops.reco.discovery.rank.author_diversity_weight`
- `ops.content.moderation.policy.review_timeout_hours`
- `ops.app.discovery.top_tabs.variant`

## 工作流设计

### 1. 治理处置工作流

#### 举报 / 审核 / 处罚主链路
`reported -> triaged -> reviewing -> action_pending -> action_applied -> closed`

补充分支：
- `reported -> dismissed`
- `reviewing -> escalated`
- `action_pending -> dual_approval_pending -> action_applied`
- `action_applied -> recovered -> closed`

#### 申诉工作流
`submitted -> evidence_pending -> under_review -> approved|rejected -> closed`

约束：
- `evidence_pending` 必须允许追加证据
- `approved` 必须产生恢复动作或撤销动作
- `rejected` 必须保留理由码与审计快照

#### 账号恢复工作流
`requested -> customer_service_intake -> evidence_verified -> dual_review -> recovered|rejected -> closed`

约束：
- 恢复必须关联原处罚动作
- `dual_review` 必须要求两位不同审批人
- 超过 SLA 必须进入工作台告警

### 2. 推荐与实验工作流

#### 实验工作流
`draft -> review_pending -> running -> ramping -> completed|rolled_back -> archived`

#### 推荐策略工作流
`draft -> simulated -> review_pending -> canary -> active -> rolled_back|retired`

#### 优化工作流
`hypothesis -> candidate_config -> offline_eval -> online_canary -> full_release|rollback`

约束：
- 任何进入 `canary` 的策略必须绑定 guardrail 指标
- `rolled_back` 必须能追溯到触发原因和 rollback token

## 推荐运营参数空间与 Guardrail

### 召回层允许项
- 白名单 / 黑名单
- 活动池 / 保底池
- 人群定向召回
- 领域 / 作者 / 圈子扶持

禁止项：
- 直接写入候选排序结果
- 绕过审计对个体用户做隐式人工干预

### 粗排层允许项
- 质量阈值
- 探索比例
- 新内容保护系数
- 风险内容预过滤阈值
- 粗排权重模板选择

### 精排 / 重排层允许项
- 模型版本选择
- 多样性权重
- 去重策略模板
- 负反馈抑制系数
- 扶持因子范围
- rerank 开关

### Guardrail

所有推荐运营动作至少绑定：
- CTR / dwell / negative feedback guardrail
- 内容生态 guardrail（作者多样性、内容新鲜度）
- 业务安全 guardrail（投诉率、处罚率、误伤率）

任何超阈值行为必须自动中止放量并进入回滚。

## 权限、审计与证据设计

### 权限模型

当前阶段不做复杂角色树，但必须支持能力级 scope：
- `ops.case.read`
- `ops.case.write`
- `ops.case.approve`
- `ops.reco.read`
- `ops.reco.write`
- `ops.experiment.write`
- `ops.audit.read`

### 危险动作模型

危险动作至少包括：
- 永久封禁
- 账号恢复
- 大范围推荐策略切换
- 实验大比例放量
- 批量下架

危险动作必须具备：
- `danger_level`
- 强制确认
- 审计记录
- 可选双签
- 回滚上下文

### 证据模型

`EvidenceAsset` 统一承载：
- 图片
- 视频
- 文本材料
- 聊天片段
- 外部链接快照

要求：
- 必须有 hash
- 必须有上传人与时间
- 必须能关联 case 与审批结论

## Codegen 与工程落点

### 生成责任

`runtime-codegen`：
- Go DTO
- Go handler scaffold
- Python schema / client
- 审计与工作流常量

`codegen_app_metadata`：
- App IA / feature flag / request metadata DTO

现有 `codegen_ops_portal_metadata`：
- TS types
- 门户菜单 schema
- workflow enum
- 表单 schema
- 对象详情 schema

### 手写责任

手写部分包括：
- 业务规则实现
- 审批判定逻辑
- 策略校验逻辑
- 推荐 guardrail 执行逻辑
- case 协调逻辑

## 部署与演进设计

### 当前态
- `product-control-plane` 逻辑独立
- 部署上可由 `seed-box` 容器承载
- 与领域处置服务同 Pod 部署

### 目标态
- `product-control-plane` 独立 Deployment / Pod
- 与 `user-plane` 分离扩缩容
- 支持按 case backlog、批处理 CPU、操作员并发进行弹性调整

### 演进约束
- 接口、对象、审计模型不能依赖同 Pod 前提
- readiness / liveness 需要预留控制面独立探针能力
- 后续演进到 `domain-plane -> process` 映射时不改 API 契约

## 与相邻节点的关系

本节点负责上位约束，不替代下游节点：
- `event-ingestion-and-analytics`
  - 负责事件 schema、指标口径、维度与报表
- `experiment-bucketing-and-rollout`
  - 负责分桶引擎、放量、实验审计与回滚
- `feedback-optimization-loop`
  - 负责反馈采集、评估与优化发布闭环

本节点统一约束：
- 产品边界
- 对象模型
- 工作流上位模型
- `product-control-plane` 契约原则
- 推荐运营深度与 guardrail 边界
- `ops.*` 与 IA 配置边界

## 适用场景与约束

适用场景：
- 多领域共用一个统一运营控制面
- 需要把治理、实验、推荐运营与端侧 IA 配置纳入统一体系
- 需要保证未来从同 Pod 组合演进到独立 Pod

约束与局限：
- 当前只冻结上位模型，不深入到每个领域对象字段级定义
- 推荐运营的参数空间与 guardrail 需要后续具体节点继续细化
- 客服工作台、附件预览、检索系统等实现细节不在本阶段展开
- 当前不扩展到 `platform-ops` 的系统治理对象

## 未来演进
- 从统一对象模型细化到领域级 `product-control-plane` schema
- 从统一工作流细化到审核、申诉、恢复、双签的状态机模板
- 从推荐运营总模型细化到召回 / 粗排 / 精排的参数空间与回滚模型
- 从 IA 配置总边界细化到 app shell / route / surface / page 级 schema
- 将高风险治理动作、推荐运营动作与审计动作接入统一集成验收与 `make gate-full`
