# L2 特性：product-control-plane-foundation

## 背景与动机

当前仓库已经分别有事件、实验、反馈优化等运营能力线，也已冻结统一门户与三类面上位规范，但 `product-ops` 仍缺少一个正式的共同产品规格，去统一：
- 一个产品、两大模块的产品形态
- 各领域 `product-control-plane` 的统一接口契约
- 审核、处罚、申诉、恢复的统一 case / workflow 模型
- 推荐运营在召回、粗排、精排/重排的统一干预边界
- `ops.*` 与端侧 IA / 体验配置的统一边界

如果不在 PRD 阶段冻结这层规格，后续会出现：
- 治理处置与增长运营分裂成多套后台与多套对象模型
- 各领域手写各自的运营接口，无法统一 codegen
- 推荐运营退化为只有 AB 分桶，没有召回与排序干预能力
- 申诉与恢复缺少统一证据、SLA、双签与审计模型

## 目标用户

- 统一运营控制面的直接使用者：运营、内容治理、客服、推荐策略维护者
- 当前组织模式下，上述角色可由全栈研发兼职承担，因此产品必须支持少角色拆分的协作方式
- 间接使用者：各垂直领域服务 owner、发布守门者、审计与合规复核者

## 功能范围

- 为 `product-ops` 统一运营控制面建立共同产品基线，第一阶段作为一个产品交付，内部包含“治理处置”和“增长/实验/推荐运营”两大模块。
- 为每个领域定义 `product-control-plane` 的统一管理接口规范，要求通过 `control_plane.yaml`、`workflow.yaml`、`audit_schema.yaml`、`config_schema.yaml` 表达，并由 codegen 生成 Web / Go / Python / App 契约。
- 为用户域冻结“主控账号 / 子账号”双层模型在运营控制面的呈现边界：`OwnerAccount` 只承担管理、恢复、通讯录匹配与组合视角，`SubAccount` 承担应用、邀请与增长归因主体。
- 冻结推荐运营深度，覆盖召回、粗排、精排/重排的受控干预，而不仅是实验分桶。
- 冻结账号恢复工作流，要求支持客服、证据上传、SLA、人工复核双签，并形成正式 case model。
- 冻结用户发展与经营基线，覆盖通讯录发现、已加入用户识别、未加入用户邀请、关系转化、分群经营与生命周期视图。
- 冻结端侧 IA 与体验配置边界，允许 `ops.*` 管理一级/二级 tab、栏目、版面、布局与体验 feature flag，但不得混入 `sys.*` 运行时参数。
- 冻结控制面部署原则：短期允许 `seed-box` 容器与领域处置服务同 Pod，共享部署；长期支持独立 Deployment / Pod 与独立扩缩容。
- 明确统一门户中的 `Product Ops` 一级菜单、二级工作域和对象跳转边界。

## 不做什么（Out of Scope）

- 不在本节点定义 `platform-ops` 的能力边界与系统治理实现
- 不在本节点详细设计所有实验算法、模型训练流程与离线特征工程
- 不在本节点展开具体 K8s / Terraform / Helm 资源细节
- 不让 `product-ops` 直接接管各领域主业务状态真相源
- 不在本节点把每个领域对象细化到字段级 schema；字段级设计留到 `/design`

## 产品范围

### 一级菜单
- 事件与指标
- 标签与分群
- 实验与灰度
- 推荐运营
- 邀请与增长
- 生命周期经营
- 内容治理
- 账号治理
- 申诉与恢复
- 客服工单
- 策略中心

### 两大模块边界

#### 治理处置
- 审核
- 投诉
- 下架
- 处罚
- 申诉
- 恢复
- 客服
- 证据
- SLA
- 双签

#### 增长 / 实验 / 推荐运营
- 事件
- 指标
- 标签
- 实验
- 活动
- 通讯录发现
- 邀请归因
- 生命周期经营
- 推荐干预
- 优化闭环

## 约束

- `product-ops` 只管理 `ops.*` 业务策略与业务事件数据
- 不管理 `sys.*` 运行时参数与 IaC
- 控制面契约不得侵入用户面 API
- 审核、处罚、申诉、恢复必须可审计
- 推荐运营只能在受限参数空间内干预
- 用户发展与增长链路必须保留“主控账号管理视角”和“子账号应用视角”的语义分层
- 通讯录匹配结果不得直接等同于社交关系；建立好友/圈子/群关系时必须落到具体子账号
- 邀请归因、奖励与传播主体默认归属于具体子账号，而不是主控账号
- 统一前端为 `React + TypeScript`
- 后端主栈为 `Go`
- 推荐训练 / 评估保留 `Python`
- 各领域必须通过 `product-control-plane` 暴露运营管理能力，不允许各领域手写第二套临时后台接口

## 对标输入与吸收结论

对标输入：
- `LaunchDarkly / Statsig / Amplitude`：实验、放量、归因与策略审计
- `TikTok / YouTube Studio / Trust & Safety`：审核、处罚、申诉、恢复、证据与客服协同

吸收结论：
- 借鉴点：统一产品壳层、实验与归因联动、治理 case/workflow、证据与双签审计
- 借鉴点：把用户增长、邀请传播、恢复治理、分群经营纳入同一工作台，而不是散落在多个后台
- 不借鉴点：不做多产品拆分，不照搬大型组织的复杂角色体系
- 适用边界：当前适合一个统一产品、少角色拆分、全栈共担的团队形态
- 成本取舍：先冻结共同上位模型，再在 `/design` 阶段按模块细化 schema 和权限模型

## 角色分工

- 产品：定义统一运营控制面的产品边界、菜单范围、治理/增长模块范围
- 架构：定义三类面边界、元数据契约、工作流上位模型、部署演进策略
- 开发：按 metadata-first 落地 `product-control-plane`、codegen、对象模型与业务逻辑
- 测试：建立 T1~T4 对应的契约、模块、集成、旅程验证
- 发布：负责灰度放量、审计校验、回滚守门与风险动作审批链

## 非功能目标

- 实时性：
  - 高风险治理动作写入后，审计记录在 5 秒内可检索
  - 实验/推荐运营配置变更在 1 分钟内可被运行时消费或明确标记为待生效
- 弱网：
  - 门户弱网场景下，表单草稿与 case 填写内容不得因刷新丢失
  - 审核、申诉、恢复等提交流程失败时必须可恢复重试并保留上下文
- 性能：
  - 一级菜单切换 P95 小于 1 秒
  - 对象详情页与工单详情页首屏 P95 小于 2 秒
  - 搜索与筛选结果返回 P95 小于 1.5 秒
- 并发 / 容量：
  - 支持同一环境下 100 名操作员并发使用
  - 支持 10 万级日事件入库、千级 case 存量与百级并发审计查询
- 弹性：
  - 短期同 Pod、长期独立 Pod 的两种部署形态都必须成立
  - 用户面扩容不依赖控制面一起扩容
- 可观测：
  - 所有高风险动作、双签动作、实验放量与回滚动作必须带 trace / request / audit 关联字段

## 元数据唯一源边界

- `service.yaml`
  - 面向用户面与对外业务 API 的 operation / method / path 契约
- `control_plane.yaml`
  - 面向 `product-control-plane` 的对象、route、operation、danger_level、approval_mode 契约
- `workflow.yaml`
  - 审核、处罚、申诉、恢复、双签、SLA 的状态机唯一真相源
- `audit_schema.yaml`
  - 审计事件、变更记录、证据关联、回滚关联的唯一真相源
- `config_schema.yaml`
  - `ops.*` 业务策略、IA 配置、体验 flag 的配置项 schema 唯一真相源
- `ui_config.yaml`
  - 具体领域页面 IA / tab / 布局配置的领域级真相源

禁止：
- 在控制台代码中手写第二套对象 schema
- 在各领域服务中手写临时运营后台接口
- 在 App / Web / Go / Python 中维护第二份字段常量或路由规则表

## 四层验收视图

- T1：控制面元数据、工作流 schema、审计 schema、配置 schema、对象模型与契约一致性
- T2：门户交互、case 流程、实验配置、推荐运营配置、风险动作确认与双签交互
- T3：`product-ops` 与 content / circle / chat / user / assistant 等领域的控制面联调
- T4：真实治理旅程、真实申诉/恢复旅程、真实实验放量与回滚旅程

## 灰度与回滚约束

- 产品灰度：
  - 统一按 `5% -> 25% -> 50% -> 100%` 放量
  - 支持按用户 / 人群 / 地域 / 渠道 / 实验层灰度
- 关键观测：
  - 治理动作失败率
  - case SLA 违约率
  - 实验 guardrail 指标异常
  - 推荐干预后关键指标回落
- 回滚条件：
  - 审计链不完整
  - guardrail 指标触发阈值
  - case 工作流状态不一致
  - 运行时消费配置失败或回退失败

## 核心对象模型

### 对象模型概要
- `ModerationCase`
- `EnforcementAction`
- `AppealCase`
- `RecoveryCase`
- `EvidenceAsset`
- `ReviewDecision`
- `EventDefinition`
- `MetricDefinition`
- `Segment`
- `Experiment`
- `InviteAttribution`
- `ContactDiscoveryMatch`
- `LifecycleProfile`
- `OwnerAccountPortfolioView`
- `RecommendationPolicy`
- `RecommendationOverride`
- `OptimizationRun`

## 工作流模型

### 工作流模型概要
- 治理处置：`reported -> triaged -> reviewing -> action_pending -> action_applied -> closed`
- 申诉：`submitted -> evidence_pending -> under_review -> approved|rejected -> closed`
- 账号恢复：`requested -> customer_service_intake -> evidence_verified -> dual_review -> recovered|rejected -> closed`
- 邀请转化：`generated -> delivered -> viewed -> accepted -> activated|expired`
- 生命周期经营：`new -> activated -> retained -> high_value|silent -> recalled|churned`
- 实验：`draft -> review_pending -> running -> ramping -> completed|rolled_back -> archived`
- 推荐策略：`draft -> simulated -> review_pending -> canary -> active -> rolled_back|retired`

## 适用范围与约束

适用范围：
- `product-ops` 统一运营控制面的共同产品基线
- 各领域 `product-control-plane` 的接口、工作流、审计与策略对象上位约束
- 用户域下 `OwnerAccount / SubAccount` 的增长、邀请、恢复、分群与生命周期经营基线
- 后续 `event-ingestion-and-analytics`、`experiment-bucketing-and-rollout`、`feedback-optimization-loop` 等节点的共同前提

约束：
- 共同对象模型是上位约束，不替代各领域对象字段级细化
- 推荐运营的参数空间与 guardrail 需要后续 `/design` 细化
- 客服工作台、附件预览、检索系统等实现细节不在本阶段展开
- 部署组合必须兼容短期同 Pod 与长期独立 Pod，不得以当前部署形态固化接口

## 验收标准概要
- A1：`product-ops` 作为统一产品的范围、两大模块与核心对象/工作流清晰冻结
- A3：各领域 `product-control-plane` 契约独立，且部署支持短期同 Pod、长期独立 Pod
- A5：推荐运营覆盖召回 / 粗排 / 精排，用户发展覆盖通讯录发现 / 邀请归因 / 生命周期经营，治理处置覆盖申诉 / 恢复 / 双签
- A7：控制面元数据、工作流、审计与 codegen 目标一致
- A8：后续 `/design` 可直接基于本节点展开方案比较与任务拆解
