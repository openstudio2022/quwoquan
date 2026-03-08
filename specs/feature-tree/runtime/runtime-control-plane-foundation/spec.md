# L2 特性：runtime-control-plane-foundation

## 功能说明
- 为 `platform-ops` 与 `product-ops` 提供统一 Web 门户 `ops-portal` 的共同上位规格，冻结门户壳层、全局导航、权限、审计、通知、环境切换与搜索入口。
- 冻结各垂直领域的三类面架构：`user-plane`、`platform-control-plane`、`product-control-plane`，要求三类面在契约层独立，并支持部署时任意组合。
- 冻结控制面元数据体系与 codegen 目标，确保 Web / Go / Python / App 共享同一份控制面真相源。
- 冻结配置分层边界：`sys.*` 归 `platform-ops`，`ops.*` 归 `product-ops`，IaC 与基础设施参数不进入业务配置中心。
- 冻结端侧可配置边界：一级/二级 tab、栏目、版面、布局与体验类 feature flag 可配置，但 long-polling 周期、超时、限流、采样率等运行时参数必须归入 `sys.*`。
- 冻结统一门户视觉与交互语义必须匹配当前应用的语义风格体系，不允许演化出割裂的第二套产品语义。
- 冻结统计仪表盘能力为统一门户的内建能力，支持总览、系统治理、实验归因、推荐效果、治理效率与审计追踪等多类 dashboard。

## 产品目标

### 目标用户
- 全栈研发：通过 `Platform Ops` 完成服务接入、配置治理、发布灰度、依赖治理、观测与回滚
- 运营/治理/客服：通过 `Product Ops` 完成事件、实验、推荐运营、审核、处罚、申诉、恢复与证据处理
- 发布与验收责任人：通过统一门户完成跨域审计、变更跟踪与统一集成验收

### 核心问题
- 当前缺少统一入口来承接 `platform-ops` 与 `product-ops` 的共同壳层能力
- 领域服务尚未形成三类面统一契约，后续拆分部署风险高
- 控制面对象、元数据、codegen、端侧 IA 配置、运行时参数尚未统一成单一真相源
- 如果本阶段不收口，后续各域开发会各自实现临时接口与临时后台

### 成功标准
- `ops-portal` 成为 `platform-ops` 与 `product-ops` 的唯一门户壳层
- 全领域形成 `user-plane / platform-control-plane / product-control-plane` 的共同契约口径
- 控制面元数据对象可作为 Web / Go / Python / App 的共同真相源
- 门户、元数据、codegen、部署组合与统一集成验收都能进入开发而不需要返工大改
- 门户在语义风格、信息层级、状态表达与危险动作反馈上与当前应用保持同一设计语言
- 门户具备业界一流水准的统计仪表盘能力，能够支撑管理决策而非只提供列表与表单

## 门户范围

### 一级菜单
- `总览`
- `Platform Ops`
- `Product Ops`
- `审计与变更`
- `系统设置`

### 二级菜单基线
- `总览`：环境态势、发布与告警、待办事项、最近变更、重点实验与治理事件
- `Platform Ops`：服务目录、配置中心、治理策略、发布灰度、环境与依赖、可观测与 SLO、Runbook 与演练、CI/CD 门禁
- `Product Ops`：事件与指标、标签与分群、实验与灰度、推荐运营、内容治理、账号治理、申诉与恢复、客服工单、策略中心
- `审计与变更`：配置变更审计、运营策略审计、处罚与恢复审计、发布记录、回滚记录、双签审批记录
- `系统设置`：门户权限、字典与枚举、通知渠道、附件与证据存储、集成配置

### 统计仪表盘基线
- `总览` 必须提供跨域经营与治理总览 dashboard：活跃告警、待办审批、发布状态、重点实验、治理 case、SLA 风险
- `Platform Ops` 必须提供系统治理 dashboard：服务健康、SLO、错误预算、灰度进度、依赖健康、发布风险
- `Product Ops` 必须提供业务运营 dashboard：事件漏斗、核心指标趋势、实验归因、推荐效果、治理效率、恢复成功率
- `审计与变更` 必须提供审计追踪 dashboard：危险动作趋势、双签通过率、回滚频次、case 时长分布

### 门户全局能力
- 全局环境切换：`local / dev / integration / prod`
- 全局身份与权限：统一登录、RBAC、危险动作确认、双签审批入口
- 全局搜索：服务、配置项、实验、case、用户、内容、圈子、发布记录、审计记录
- 全局通知：告警、审批、case SLA、灰度中断、回滚事件
- 全局审计：所有变更与处置统一可检索
- 全局工作台：待办、我发起、我审批、我关注、我负责
- 全局对象跳转：任意业务对象可在门户中跨域跳转到对应控制面详情页
- 全局 dashboard 能力：统一指标卡、趋势图、分布图、漏斗、对比视图、钻取下钻与时间范围切换
- 全局风格语义：页面层级、卡片层级、危险状态、成功反馈、空态、加载态、审批态必须与当前应用语义风格一致

## 适用范围与约束

适用范围：
- 作为 `platform-ops` 与 `product-ops` 的共同上位规格
- 作为统一控制面元数据、统一 codegen、统一部署组合与统一集成验收的基线
- 作为后续各领域接入控制面时的强约束

约束：
- 统一门户前端技术栈冻结为 `React + TypeScript`
- 控制面后端主栈冻结为 `Go`
- 推荐训练、离线分析、模型评估等计算型能力保留 `Python`
- 控制面接口禁止手写第二套临时 admin / ops API，必须由元数据和 codegen 驱动
- 三类面契约不得依赖当前部署拓扑，不得以“先混合、后拆分”为前提
- 每个领域必须能够支持三类面在部署期任意组合，避免后期返工

## 业务范围

### In Scope
- 统一门户壳层与全局能力
- 门户菜单、对象跳转、全局搜索、全局通知、全局工作台
- 门户风格语义、状态语义与信息层级规范
- 统一统计仪表盘能力与 dashboard 元数据承载边界
- 三类面架构与领域服务接入模板
- 控制面元数据对象基线与字段级设计约束
- codegen 责任边界与产物边界
- `sys.*` / `ops.*` / IaC 配置分层
- 端侧 IA / 布局 / 体验 flag 与运行时参数分层
- 领域服务最低接入矩阵
- 统一集成验收口径

### Out Of Scope
- `platform-ops` 具体页面交互细节与后端实现
- `product-ops` 具体工作流实现与策略算法实现
- K8s、Terraform、Helm 的具体模板文件
- 每个领域的具体审核规则、推荐权重、运营活动细节
- 真正的统一门户前端代码与控制面后端代码实现
- BI 数仓、指标 ETL、图表引擎的具体实现细节

## 借鉴输入

借鉴点：
- `Backstage + Argo Rollouts`：统一研发自助入口、服务目录、发布与灰度治理
- `LaunchDarkly / Statsig / Amplitude`：实验、灰度、指标归因、策略审计
- `TikTok / YouTube Studio / Trust & Safety`：治理处置、申诉恢复、证据与审计工作流

不直接照搬：
- 不引入过重的 mesh-first 平台体系
- 不让控制台绕过 repo / metadata 直接成为唯一真相源
- 不将业务治理逻辑直接硬编码在控制面 UI 或脚本中

## 职责边界

本节点负责：
- 统一门户壳层
- 三类面架构基线
- 控制面元数据对象基线
- 领域服务业务对象接入规范
- codegen 产出目标基线
- 控制面部署组合基线
- 统一集成验收口径

本节点不负责：
- `platform-ops` 的详细产品设计与实施细节
- `product-ops` 的详细产品设计与实施细节
- 各具体领域的治理动作、推荐策略、审核流程细节
- 具体 K8s / Terraform / Helm 模板实现

## 角色与职责

### 本节点负责统一的内容
- 门户：壳层、菜单、导航、权限入口、通知、搜索、对象跳转
- 风格：与当前应用一致的语义风格、状态语义与危险动作语义
- dashboard：总览、系统治理、业务运营、审计追踪的共同能力与元数据边界
- 契约：三类面、对象视图、控制面动作、部署组合原则
- 元数据：6 类控制面元数据对象
- 工具链：codegen 产物边界与统一集成验收口径

### 下游节点负责的内容
- `platform-ops`：平台功能模块的对象、页面、流程、字段、策略与交互
- `product-ops`：运营/治理/实验/推荐模块的对象、页面、流程、字段与交互
- 各领域服务：对象级动作、DTO、权限、状态机与实现

## 领域服务业务对象接入规范

### 三类面下的业务对象归属

每个领域服务的业务对象必须按三类面拆分其“可见对象视图”，而不是复制三份主数据：

- `user-plane object view`
  - 面向 App / Gateway / Orchestrator
  - 仅暴露用户旅程所需字段与动作
- `platform-control-plane object view`
  - 面向 `platform-ops`
  - 暴露服务、配置、依赖、治理、发布、健康、容量、审计等系统对象
- `product-control-plane object view`
  - 面向 `product-ops`
  - 暴露内容治理、账号治理、实验、推荐运营、case/workflow、业务分析等对象

约束：
- 三类面共享同一业务主对象真相源，不允许复制主状态并形成双写主库
- 控制面只能读取或触发受控动作，不得私自重建业务聚合
- 控制面 DTO、对象视图、动作能力必须由元数据声明与 codegen 产出

### 领域服务接入完成定义

一个领域若要被认定为“已接入统一控制面”，至少必须满足：
- 已声明 `user-plane` / `platform-control-plane` / `product-control-plane`
- 已声明最低对象集合与最低动作集合
- 已声明用户面字段与控制面字段的可见性边界
- 已声明危险动作与双签动作
- 已声明控制面依赖对象与审计要求
- 已经通过元数据与 codegen 产出统一契约

### 控制面可接入对象类型

领域服务接入控制面时，至少要能识别以下对象类别：
- `ServiceObject`：服务、版本、依赖、环境、实例、健康、SLO、发布单
- `ConfigObject`：`sys.*` / `ops.*` 配置项、配置包、灰度版本、回滚记录
- `GovernanceObject`：超时、重试、熔断、限流、降级、告警策略、runbook
- `BusinessObject`：内容、评论、圈子、会话、用户、助手 run、实验、策略
- `CaseObject`：举报、审核单、处罚单、申诉单、恢复单、双签审批单
- `EvidenceObject`：附件、截图、录屏、证据文件、外链证据
- `AnalyticsObject`：指标定义、维度、分群、实验结果、推荐效果、审计事件

### 全领域最低接入矩阵

| 领域 | `user-plane` 主对象 | `platform-control-plane` 最低对象 | `product-control-plane` 最低对象 |
|---|---|---|---|
| `content` | feed / post / comment / media | ServiceObject / ConfigObject / GovernanceObject / AuditRecord | 举报 / 下架 / 审核 / 推荐运营 / 内容统计 |
| `circle` | circle / member / feed / file | ServiceObject / ConfigObject / GovernanceObject | 圈子治理 / 成员处置 / 精选 / 推荐运营 |
| `chat` | conversation / message / member | ServiceObject / ConfigObject / GovernanceObject / SLOObject | 审计读取 / 投诉 / 敏感治理 / 会话治理 |
| `user` | profile / auth / persona / setting | ServiceObject / ConfigObject / GovernanceObject / AuditRecord | 处罚 / 申诉 / 恢复 / 客服工作流 |
| `assistant` | run / context / skill-consent | ServiceObject / ConfigObject / GovernanceObject / DependencyProfile | 反馈学习 / 策略管理 / 实验 / 审核 |
| `integration` | location / external adapter view | ServiceObject / ConfigObject / DependencyProfile | 外部 provider SLA / 风险治理 / 审计 |
| `notification` | notification / template delivery view | ServiceObject / ConfigObject / GovernanceObject | 模板治理 / 渠道策略 / 发送审计 |
| `recommendation` | feed scoring / feature query view | ServiceObject / ConfigObject / DependencyProfile / ModelProfile | 实验 / 推荐运营 / 模型版本 / 优化评估 |
| `realtime` | connection / push channel | ServiceObject / ConfigObject / GovernanceObject / SLOObject | 会话通道治理 / 审计读取 |
| `rtc` | call session / room view | ServiceObject / ConfigObject / DependencyProfile / SLOObject | 通话治理 / 申诉证据 / 审计读取 |

## 控制面元数据对象基线

### 必需元数据对象
- `portal_shell.yaml`
  - 定义门户壳层、环境上下文、全局工作台、全局搜索、通知入口
- `portal_menu.yaml`
  - 定义一级/二级菜单、路由、权限、对象跳转与可见条件
- `control_plane.yaml`
  - 定义三类面、route、operation、scope、危险级别、审计要求、部署属性
- `config_schema.yaml`
  - 定义 `sys.*` / `ops.*` 配置项 schema、scope、reload、rollout、risk_level
- `workflow.yaml`
  - 定义审核、处罚、申诉、恢复、双签、SLA 等状态机
- `audit_schema.yaml`
  - 定义审计事件模型、变更模型、追责字段、证据引用、回滚关联

### 元数据与现有业务 metadata 的关系
- 控制面元数据与 `contracts/metadata/{domain}/{entity}` 平行存在，不覆盖业务 metadata
- 业务 metadata 继续定义领域对象、字段、事件、服务契约
- 控制面元数据定义对象视图、控制面动作、门户路由、dashboard 视图、工作流、审计与配置 schema
- 两者必须共享统一命名、owner、domain / entity / object_type、错误码与审计字段口径

## 门户语义风格约束

### 统一语义来源
- 统一门户必须继承当前应用的页面语义与层级语义，不允许形成独立的后台审美体系
- 必须对齐 `specs/ux/page-layout-semantics.md` 所体现的页面结构、状态表达与操作分级原则
- 必须对齐 `AppTypography`、`AppSpacing`、`AppColors` 这一组语义 token 思路，Web 侧允许映射为同义 design token，但不允许改变语义层级

### 强制风格约束
- 页面必须保持“顶部导航区 / 内容区 / 底部操作区”的清晰三区语义
- 列表、表单、详情、dashboard 卡片必须保持统一的信息密度梯度
- 危险动作、双签动作、可回滚动作、成功反馈、空态与加载态必须与 App 侧语义一致
- 门户虽然是 Web，但交互语义必须延续当前应用的“清晰层级、轻量分组、强状态反馈、少噪声装饰”的风格

### 行业对标目标
- 不做传统陈旧 admin 风格，不接受密集表格堆砌、颜色泛滥、信息层级混乱
- 对标一流控制台体验：信息可扫读、状态可定位、风险可识别、动作可回溯、dashboard 可决策

### 元数据强约束
- 任何控制面 API、对象模型、表单 schema、工作流状态机，必须先有元数据再有代码
- Web、Go、Python、App 消费的是同一份元数据语义，不允许维护第二真相源
- 控制面元数据与业务 metadata 平行演进，但必须共享统一 naming、owner、scope、audit 口径
- 新增领域控制面接入时，顺序必须是：
  - 元数据对象更新
  - `make verify`
  - codegen
  - 手写业务逻辑
  - 契约测试与集成验收

## 非功能规格

### 实时性
- 门户全局搜索与全局对象跳转：常规查询目标 `p95 < 800ms`
- 配置项读取与对象详情查询：目标 `p95 < 500ms`
- 灰度状态、审批待办、case SLA 视图：目标分钟级一致

### 弱网与容错
- 门户在弱网下应支持只读重试与显式错误态
- 高风险动作提交必须幂等并可追踪
- 配置发布、处罚、恢复、回滚等危险动作失败时必须保留中间状态与审计记录

### 并发与扩展
- 用户面按用户流量扩缩容
- 控制面按审批量、查询量、case backlog、发布窗口与批处理压力扩缩容
- 门户壳层不得绑定单域数据源

### 安全与审计
- 所有危险动作必须要求权限校验与审计
- 双签动作必须有显式审批链
- 审计记录必须可关联环境、actor、object、action、before/after、release/version

### 可观测与 dashboard
- 统一门户 dashboard 默认支持环境切换、时间范围、对象过滤、下钻和回跳
- dashboard 卡片必须支持从聚合指标跳转到对象列表、详情页与审计记录
- dashboard 不得成为第二指标真相源，指标定义仍归 `AnalyticsObject` / 业务 metadata / 统计口径定义

## 核心约束
- 所有领域必须支持三类面：`user-plane`、`platform-control-plane`、`product-control-plane`
- 所有领域的控制面能力必须通过统一控制面元数据表达并 codegen
- 允许短期使用 `seed-box` 独立容器与领域处置服务同 Pod 部署
- 长期必须支持控制面独立 Deployment / Pod 与独立扩缩容
- `platform-control-plane` 与 `product-control-plane` 在逻辑上独立，部署上可合可分
- 端侧 IA / 布局 / 栏目 / 体验 flag 属于 `ops.*`
- long-polling 周期、超时、限流、采样率等运行时参数属于 `sys.*`

## 验收标准概要
- A1：统一门户壳层、菜单、全局能力边界明确，且可作为两大控制面的共同上位规格
- A3：三类面与部署任意组合原则冻结，支持短期同 Pod、长期独立 Pod
- A4：审计、通知、环境切换、搜索与全局导航在门户层有统一口径
- A5：`sys.*` / `ops.*` / IaC 分层清晰，端侧可配置边界冻结
- A7：控制面元数据对象、codegen 目标与运行时约束一致
- A8：统一集成验收链路可落到 metadata、codegen、部署组合和门户壳层验证
- 门户风格语义与当前应用一致，且 dashboard 能满足总览、治理、运营、审计四类核心场景

## 开发准入判断

本节点进入开发前，必须满足：
- 控制面元数据对象达到字段级 schema 粒度
- 领域服务全量最低接入矩阵已冻结
- codegen 责任边界已冻结
- `domain-plane -> process` 演进模型已冻结
- 统一集成验收候选链路已冻结
