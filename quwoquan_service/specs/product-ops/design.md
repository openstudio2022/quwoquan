# product-ops 设计方案

## 设计动因

`product-ops` 需要作为统一产品运营控制面，承接：
- 事件与指标
- 标签与分群
- 实验与业务灰度
- 推荐运营
- 内容治理
- 账号治理
- 申诉与恢复
- 客服与证据
- `ops.*` 业务配置

当前如果只冻结 `spec.md`，还不足以支撑 `/dev`，因为仍缺：
- 统一门户里的信息架构与仪表盘模型
- `product-control-plane` 的对象/动作 metadata 基线
- workflow / audit / config 的首版样例
- codegen 与手写边界
- 与当前 App 语义风格一致的门户交互规范

## 上游输入评审

### spec 评审

当前 `spec.md` 已冻结：
- 一个产品、两大模块
- `product-control-plane` 契约独立
- 推荐运营覆盖召回 / 粗排 / 精排 / 重排
- 账号恢复要求客服工作流、证据、SLA、双签
- `ops.*` 与端侧 IA / 体验配置边界

结论：
- `spec.md` 稳定，可进入设计与 metadata 基线阶段。

### acceptance 评审

本轮补齐服务级 `acceptance.yaml`，确保：
- 至少 8 条核心验收项
- 覆盖对象、workflow、推荐干预、审计、部署、仪表盘与 codegen

### 设计阻塞检查

当前无阻塞依赖，但有两类后续落地前置：
- 需要把 `_control_plane/product/*` 正式作为首版样例输入
- 需要在现有 codegen 基础上补齐 Web / Go / Python / App 契约覆盖面

## 对标输入分析

### 对标对象
- `Trust & Safety Console` 类治理后台
- `Experiment / Feature Flag Platform`
- `Recommendation Ops Console`
- `Datadog / Grafana` 风格的业务运营大盘

### 借鉴点
- 统一工作台，先看待办、风险、SLA 与放量状态
- 高风险动作必须显示审批链、证据、审计与回滚上下文
- 推荐与实验必须自带 guardrail，不允许只给“放量按钮”
- 仪表盘必须支持从总览下钻到对象详情与 case 时间线

### 不借鉴点
- 不拆成多个独立站点
- 不引入过重的复杂 RBAC 与多组织模型
- 不允许手写散落的“临时运营后台 API”

### 当前差距
- `product-control-plane` 还没有正式 service-level 设计基线
- 样例 metadata 还未与服务级设计文档挂钩
- 门户风格与 App 语义风格的关系还未在 `product-ops` 范围内明确

## 方案对比

### 方案 A：一个统一产品，两大模块

**优点**：
- 统一壳层、搜索、通知、审计、工作台
- case、实验、策略、证据可共享交互模式
- 适合当前“全栈共担、少角色拆分”的组织方式

**缺点**：
- 信息架构与权限粒度设计要求高

**适用条件**：
- 当前阶段最适合

### 方案 B：治理处置与增长推荐拆成两个独立产品

**优点**：
- 垂直边界更清晰

**缺点**：
- 门户能力重复建设
- 审计、搜索、证据、工作台分裂
- 与当前统一门户路线冲突

**适用条件**：
- 后续组织或容量显著放大后再考虑

### 方案 C：只做事件/实验，不纳入治理处置

**优点**：
- 初期实现较轻

**缺点**：
- 无法形成统一产品运营控制面
- 申诉、恢复、双签、证据继续散落在各领域

**适用条件**：
- 不满足当前目标

## 选型决策

**选定方案**：方案 A

**理由**：
- 与统一 `ops-portal` 的路线一致
- 能复用统一壳层、审计、工作台、搜索与仪表盘
- 能把治理处置和增长推荐运营纳入同一对象模型与验收链路

## 关键设计决策

- 决策 1：`product-ops` 作为一个统一产品交付，内部保留“治理处置”和“增长 / 实验 / 推荐运营”两个模块。
- 决策 2：统一门户中的 `Product Ops` 工作域必须具备业务总览仪表盘，不允许只有列表页没有大盘。
- 决策 3：门户风格必须与当前 App 的语义风格一致，强调对象语义、状态语义、危险动作语义，不走传统粗放后台模板。
- 决策 4：`_control_plane/product/control_plane.yaml`、`workflow.yaml`、`audit_schema.yaml`、`config_schema.yaml` 正式冻结为首版样例 metadata baseline。
- 决策 5：所有高风险治理动作、推荐策略切换与实验大比例放量，必须绑定审计与回滚上下文。
- 决策 6：推荐运营只能在受限参数空间内干预，不得替代算法代码主逻辑。

## 门户风格与仪表盘

### 风格对齐原则

门户虽然是 Web 控制台，但在信息语义上要与当前 App 一致：
- 使用统一状态语义：正常、告警、风险、冻结、待审批
- 使用统一对象头部：对象摘要、当前状态、责任人、最近变更
- 使用统一时间线模式：case、实验、策略、回滚都以事件时间线展示
- 使用统一危险动作模式：危险区、确认、审批、审计、回滚入口

### `Product Ops` 总览仪表盘

一级入口需要具备以下卡片与图表：
- 待处理治理 case 数
- 超 SLA case 数
- 正在运行实验数
- 正在灰度的推荐策略数
- 处罚 / 恢复 / 申诉趋势
- 推荐 guardrail 异常趋势
- 关键业务指标趋势
- 风险告警与待审批列表

### 下钻要求

- 从大盘可以下钻到 case 列表、策略列表、实验详情
- 从对象详情可以回到大盘过滤上下文
- 从告警可以直达相关 case / experiment / recommendation_policy

## 对象模型

### 治理处置对象

| 对象 | 说明 | 关键字段 |
|---|---|---|
| `ModerationCase` | 举报、审核、处罚主 case | `caseId`, `caseType`, `targetType`, `status`, `priority`, `riskLevel`, `ownerId`, `slaPolicyId` |
| `EnforcementAction` | 处罚、下架、恢复动作 | `actionId`, `caseId`, `actionType`, `scope`, `approvalMode`, `status` |
| `AppealCase` | 申诉 case | `appealId`, `sourceCaseId`, `appellantId`, `status`, `reviewResult` |
| `RecoveryCase` | 账号恢复 case | `recoveryId`, `userId`, `customerServiceTicketId`, `slaDeadlineAt`, `dualApprovalRequired`, `finalDecision` |
| `EvidenceAsset` | 证据对象 | `evidenceId`, `caseId`, `assetType`, `storageUrl`, `hash`, `uploadedBy` |
| `ReviewDecision` | 审核与复核记录 | `decisionId`, `caseId`, `reviewerId`, `decision`, `reasonCode` |

### 增长与推荐运营对象

| 对象 | 说明 | 关键字段 |
|---|---|---|
| `EventDefinition` | 事件 schema | `eventType`, `version`, `requiredFields`, `dimensions`, `owner` |
| `MetricDefinition` | 指标定义 | `metricId`, `category`, `formula`, `dimensions`, `guardrails` |
| `Segment` | 标签与分群 | `segmentId`, `populationRule`, `includedTags`, `excludedTags`, `estimatedSize` |
| `Experiment` | 实验与放量对象 | `experimentId`, `layer`, `variants`, `targetSegments`, `rolloutPlan`, `status` |
| `RecommendationPolicy` | 推荐策略定义 | `policyId`, `scenario`, `layer`, `policyType`, `targetSegments`, `status`, `version` |
| `RecommendationOverride` | 推荐受控干预对象 | `overrideId`, `policyId`, `overrideScope`, `parameterSpace`, `effectiveWindow`, `rollbackToken` |
| `OptimizationRun` | 优化评估闭环 | `runId`, `baselineVersion`, `candidateVersion`, `evaluationMetrics`, `decision` |

## 元数据唯一源分层

### `_shared/control_plane.yaml`
承载：
- plane、danger、approval、deployment profile 等跨域公共语义
- object / operation schema 的公共字段要求

### `_control_plane/product/control_plane.yaml`
承载：
- `product-control-plane` 的对象视图、路由、动作、scope、危险级别
- 首版对象样例：`moderation_case`、`recovery_case`、`experiment`、`recommendation_policy`

### `_control_plane/product/workflow.yaml`
承载：
- 治理、申诉、恢复、实验、推荐策略的状态机
- SLA 与审批要求

### `_control_plane/product/audit_schema.yaml`
承载：
- 高风险治理和策略动作的审计字段
- 审批链、证据引用、rollback token、guardrail snapshot

### `_control_plane/product/config_schema.yaml`
承载：
- `ops.*` 的业务配置样例
- 审核策略、推荐参数、实验、端侧 IA 配置

### 禁止的第二真相源

- 禁止门户手写另一套对象字段定义
- 禁止服务端手写另一套危险动作口径
- 禁止在 Web / Go / Python / App 里分别硬编码不同的工作流状态集

## 工作流设计

### 治理处置

- 举报 / 审核 / 处罚：`reported -> triaged -> reviewing -> action_pending -> action_applied -> closed`
- 申诉：`submitted -> evidence_pending -> under_review -> approved|rejected -> closed`
- 账号恢复：`requested -> customer_service_intake -> evidence_verified -> dual_review -> recovered|rejected -> closed`

### 增长与推荐运营

- 实验：`draft -> review_pending -> running -> ramping -> completed|rolled_back -> archived`
- 推荐策略：`draft -> simulated -> review_pending -> canary -> active -> rolled_back|retired`

### 高风险约束

- 永久处罚、账号恢复、批量下架、推荐策略大范围切换、实验大比例放量必须带审批与审计
- 超 SLA case 必须进入工作台与总览告警
- 所有进入 `canary` 的策略必须绑定 guardrail

## 推荐运营参数空间与 Guardrail

### 召回层
- 白名单 / 黑名单
- 活动池 / 保底池
- 人群定向召回
- 作者 / 圈子 / 内容扶持

### 粗排层
- 质量阈值
- 探索比例
- 新内容保护系数
- 风险内容预过滤阈值

### 精排 / 重排层
- 模型版本选择
- 多样性权重
- 去重策略模板
- 负反馈抑制系数
- 扶持因子范围
- rerank 开关

### Guardrail

至少绑定：
- CTR / dwell / negative feedback
- 作者多样性 / 内容新鲜度
- 投诉率 / 处罚率 / 误伤率

任何超阈值放量必须自动停止并进入回滚。

## TDD / ATDD 策略

- ATDD：先验收对象、workflow、推荐干预、审计、仪表盘与部署演进
- TDD：
  - 先写 metadata contract tests
  - 再写 codegen snapshot tests
  - 再写门户 workflow / 表单 / 时间线交互测试
  - 最后写领域联调与真实灰度演练

## Story 与测试层映射

- Story 1：治理对象与 workflow metadata
  - T1：schema 与状态机 contract
  - T3：举报 -> 审核 -> 处罚 -> 恢复联调
- Story 2：推荐与实验对象
  - T1：config / control plane contract
  - T3：实验 -> 放量 -> 回滚联调
- Story 3：审计与证据
  - T1：audit schema contract
  - T2：时间线与审批交互
  - T3：危险动作回滚验证
- Story 4：门户与仪表盘
  - T2：门户信息架构与 dashboard 交互
  - T3：对象下钻与告警跳转联调

## 权限、审计与证据设计

- 当前阶段按能力级 scope 控制：`ops.case.read`、`ops.case.write`、`ops.case.approve`、`ops.reco.read`、`ops.reco.write`、`ops.experiment.write`、`ops.audit.read`
- `EvidenceAsset` 必须有 hash、上传人与时间，并可关联 case 与审批结论
- 所有危险动作必须产出审计记录与回滚上下文

## Codegen 分工

### `runtime-codegen`
负责：
- Go DTO
- Go handler scaffold
- Python schema / client
- workflow / audit 常量

### `codegen_app_metadata`
负责：
- App IA / feature flag / request metadata 的只读 DTO

### `codegen_ops_portal_metadata`
现有工具负责：
- TS types
- workflow enum
- 表单 schema
- 对象详情 schema
- dashboard schema
- API client

## 部署与演进设计

- 逻辑上 `product-control-plane` 独立于 `user-plane`
- 短期允许 `seed-box` 同 Pod
- 长期必须支持独立 Deployment / Pod 与独立扩缩容
- 契约与审计模型不得依赖同 Pod 事实

## 未来演进

- 细化各领域 `product-control-plane` metadata 模板
- 细化客服工作台、附件预览、检索与证据管理
- 将统一治理动作、推荐运营动作与审计动作接入 `make gate-full`
- 将仪表盘 schema 正式纳入 metadata-first
