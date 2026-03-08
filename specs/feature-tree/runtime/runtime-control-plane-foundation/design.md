# Design：runtime-control-plane-foundation

## 设计动因

当前仓库已经分别存在 `platform-ops-governance` 与 `product-ops-growth` 两条横切能力线，但缺少一个共同上位规格来统一以下问题：
- 统一 Web 门户 `ops-portal` 的壳层与菜单
- 各领域三类面的共同契约基线
- 控制面元数据对象的统一定义
- codegen 的统一输出目标
- 短期同 Pod / 长期独立 Pod 的部署演进约束

如果没有共同上位规格，后续很容易出现：
- `platform-ops` 与 `product-ops` 分别定义两套门户壳层与菜单模型
- 各领域控制面接口各自手写、各自命名
- 三类面在逻辑上混合，后续拆分 Deployment 返工
- App / Go / Python / Web 各自维护第二份控制面契约

## 上游评审结论

当前 `spec.md` 已完成 PRD 基线冻结，本文件需要补齐开发前所需的剩余设计信息：
- 字段级 metadata schema
- 领域服务对象接入模板
- codegen 分工与产物路径
- `domain-plane -> process` 演进模型
- 统一集成验收候选链路

本轮 `/design` 完成后，本节点进入 `DEV_READY_FOR_FOUNDATION` 状态，可支撑后续统一门户、领域接入与统一集成验证开发。

## 方案对比

### 方案 A：两个独立门户，分别服务 Platform/Product

优点：
- 各自边界清晰
- 前端实现可独立节奏推进

缺点：
- 门户壳层、权限、审计、搜索、通知、环境切换重复建设
- 用户心智割裂
- 两条控制面更容易演化出两套元数据和两套交互规范

结论：
- 不选。适合组织规模更大、角色更明确的团队，不适合当前全栈共担模式。

### 方案 B：统一门户壳层，后端按域分离

优点：
- 登录、权限、审计、搜索、通知、环境切换统一
- 便于建立共同的控制面元数据和 codegen 体系
- 更符合“一个团队维护、多域协作”的现状
- 后端仍能按 `platform-ops` / `product-ops` 保持清晰边界

缺点：
- 门户壳层需要更强的菜单、权限、环境上下文治理
- 需要提前设计跨域导航与审计口径

结论：
- 选择此方案。

## 关键决策

### 1. 门户形态
- 统一门户命名为 `ops-portal`
- 门户前端技术栈冻结为 `React + TypeScript`
- 初期采用单前端应用 + 域模块化，不提前引入微前端
- 门户只承载壳层、导航、全局能力与统一 UX 规范；业务能力仍由 `platform-ops` 与 `product-ops` 两个后端域提供

### 1.1 门户模块分层

门户采用四层结构：
- `shell`
  - 登录态、环境切换、全局导航、搜索、通知、审计入口、工作台
- `platform-domain`
  - `Platform Ops` 一级域下的功能模块
- `product-domain`
  - `Product Ops` 一级域下的功能模块
- `shared-foundation`
  - RBAC、表格、表单、schema 渲染、对象详情、时间线、审批、附件、diff、审计面板

推荐工程目录：
- `apps/ops-portal/`
- `apps/ops-portal/src/shell/`
- `apps/ops-portal/src/domains/platform-ops/`
- `apps/ops-portal/src/domains/product-ops/`
- `apps/ops-portal/src/shared/`

### 1.2 门户全局能力设计

统一门户必须内建以下全局能力：
- 环境上下文：当前环境、当前租户/空间、当前发布窗口
- 全局搜索：支持对象类型、领域、环境、时间范围过滤
- 全局通知：审批、告警、case SLA、灰度中断、回滚结果
- 全局审计：所有危险动作、配置变更、处置动作可统一检索
- 全局工作台：我发起、我审批、待处理、超 SLA、关注对象
- 全局对象跳转：服务、内容、用户、圈子、实验、case、配置项可跨模块跳转
- 全局 dashboard：统一指标卡、趋势图、分布图、漏斗图、排行、明细钻取、时间窗对比

### 1.2.1 门户语义风格对齐

统一门户不是传统独立后台，而是当前应用设计语言在 Web 管理面的延展。设计冻结如下：
- 信息架构延续当前应用的清晰分区语义：顶部导航区、内容区、底部动作区
- 视觉 token 必须映射当前应用的 `AppTypography`、`AppSpacing`、`AppColors` 语义层级
- 危险动作、成功反馈、空态、加载态、审批态必须延续当前应用的状态语义
- 不允许做成另一套“重表格、重线框、低层级感知”的传统 admin 风格

Web 侧建议采用同义 design token：
- `PortalTypography.*` 对齐 `AppTypography.*`
- `PortalSpacing.*` 对齐 `AppSpacing.*`
- `PortalColors.*` 对齐 `AppColors.*`
- `PortalSemanticState.*` 对齐 App 的 danger/success/warning/loading/empty/disabled 语义

### 1.2.2 门户页面布局语义

统一门户页面采用三段式语义：
- `PageHeader`
  - 页面标题、环境上下文、breadcrumb、主操作、辅助筛选入口
- `PageContent`
  - 列表、详情、表单、dashboard、时间线
- `PageFooterActionBar`
  - 危险动作确认、批量操作、审批动作、取消/提交

约束：
- dashboard 首页允许弱化 footer，但危险动作页必须保留显式动作区
- 列表页与 dashboard 页必须支持清晰的筛选区和结果区分离
- 详情页必须支持“概要卡片 + 状态时间线 + 操作区 + 审计区”的分层

### 1.3 门户壳层 schema

`portal_shell.yaml` 的推荐结构：

```yaml
version: 1
portal_id: ops-portal
title: Quwoquan Ops Portal
supported_environments: [local, dev, integration, prod]
default_environment: integration
context_switchers:
  - id: environment
    type: enum
    required: true
  - id: domain
    type: entity_ref
    required: false
workbench_views:
  - id: my-todos
    object_types: [approval, case, release]
  - id: watchlist
    object_types: [service, experiment, case]
global_search:
  types:
    - service
    - config_item
    - audit_record
    - moderation_case
    - experiment
notification_channels:
  - in_portal
  - webhook
danger_action_defaults:
  confirm_required: true
  audit_required: true
dashboard_defaults:
  time_ranges: [1h, 24h, 7d, 30d]
  chart_types: [metric_card, line, bar, pie, table, funnel]
```

字段约束：
- `portal_id`：固定为 `ops-portal`
- `supported_environments`：必须覆盖 `integration` 与 `prod`
- `context_switchers`：只定义门户上下文，不定义业务对象查询条件
- `danger_action_defaults`：定义默认危险动作要求，下游可升级，不能降级
- `dashboard_defaults`：定义门户层统一 dashboard 交互基线，不替代业务指标口径

### 1.4 菜单与对象跳转 schema

`portal_menu.yaml` 的推荐结构：

```yaml
version: 1
menus:
  - menu_id: platform-ops
    label: Platform Ops
    kind: primary
    route_id: portal.platform.home
    default_child: platform.service-catalog
    required_scopes: [platform.read]
    order: 20
  - menu_id: platform.service-catalog
    parent_menu_id: platform-ops
    label: 服务目录
    kind: leaf
    route_id: platform.service-catalog
    surface_id: ops.portal.platform.service_catalog
    object_types: [service, plane_binding]
    visible_when:
      any_scopes: [platform.read]
    order: 10
jump_rules:
  - object_type: service
    route_id: platform.service-detail
  - object_type: moderation_case
    route_id: product.case-detail
dashboard_views:
  - dashboard_id: portal.overview
    route_id: portal.overview
    widgets:
      - active_alerts
      - pending_approvals
      - release_status
```

字段约束：
- `menu_id`：全局唯一，采用 `domain.submodule` 风格
- `route_id`：必须是 codegen 常量，不允许前端手写 path 真相源
- `surface_id`：必须与页面/表单/详情页消费的 metadata 对齐
- `visible_when`：只允许声明可见条件，不承担鉴权本体；真正权限仍以 `required_scopes` 判定
- `jump_rules`：对象跳转只按 `object_type -> route_id` 绑定，不允许写前端硬编码跳转表
- `dashboard_views`：声明 dashboard 入口与 widget 编排，但不承载指标计算逻辑

### 1.5 权限绑定模型

统一 RBAC 绑定采用四层：
- `role`
- `scope`
- `action`
- `approval_requirement`

规则：
- 菜单可见性由 `required_scopes` 决定
- 危险动作执行由 `action + scope + approval_requirement` 决定
- 双签动作必须在 `control_plane.yaml` 中声明 `approval_mode=dual`
- 不允许只靠前端路由守卫实现权限
- dashboard 查看权限与危险动作权限分离，默认只读 dashboard scope 不得自动授予写操作

### 1.6 仪表盘设计基线

门户 dashboard 至少覆盖四大类：
- `overview-dashboard`
  - 发布状态、待办审批、风险告警、重点实验、重点 case、异常趋势
- `platform-dashboard`
  - 服务健康、SLO、错误预算、依赖健康、灰度进度、回滚历史
- `product-dashboard`
  - 核心指标、事件漏斗、实验归因、推荐效果、治理效率、恢复成功率
- `audit-dashboard`
  - 高危动作趋势、双签通过率、case 周期、配置变更热区、回滚频次

仪表盘交互要求：
- 默认支持环境、领域、对象、时间范围筛选
- 每个 widget 必须能下钻到列表、详情或审计视图
- 每个趋势图必须标注口径、时间窗与聚合方式
- 空态必须显示“暂无数据 / 未配置 / 无权限”的差异语义

## 2. 三类面架构

### 2.1 三类面职责模型

#### `user-plane`
- 面向 App、Gateway、Orchestrator
- 聚焦用户旅程、读写业务主流程
- 面向高流量、高弹性、低管理开销

#### `platform-control-plane`
- 面向 `platform-ops`
- 聚焦系统治理、配置、依赖、健康、发布、SLO、审计
- 面向低频但高风险变更

#### `product-control-plane`
- 面向 `product-ops`
- 聚焦业务对象治理、实验与推荐运营、工单与工作流、业务分析
- 面向低频写、多维查询、批处理与审核协同

### 2.2 三类面与业务对象的关系

三类面不是三套主数据，而是三种对象视图：
- 用户面：用户对象视图
- 平台控制面：系统对象视图
- 产品控制面：治理/运营对象视图

任何领域对象都必须遵守：
- 主状态仍归领域服务
- 控制面只能通过受控动作变更主状态
- 控制面不得维护脱离领域主状态的并行主库

### 2.3 领域服务对象接入模板

每个领域在接入控制面时，都要补齐以下 9 项：
- `domain`
- `entity/object_type`
- `plane`
- `view_fields`
- `control_actions`
- `danger_actions`
- `approval_mode`
- `audit_events`
- `deployment_profile`

推荐模板：

```yaml
domain: content
object_type: post
planes:
  user-plane:
    view_fields: [id, author_id, body, media, stats]
    actions: [create, update, publish, delete]
  platform-control-plane:
    view_fields: [service_version, config_refs, dependency_status, slo_status]
    actions: [read_config, apply_governance, release_config, rollback_config]
  product-control-plane:
    view_fields: [moderation_status, recommendation_labels, report_count]
    actions: [submit_case, takedown, restore, add_policy_override]
danger_actions:
  - takedown
  - rollback_config
approval_mode:
  takedown: dual
audit_events:
  - post.takedown.applied
  - post.recommendation_override.created
deployment_profile: seed-box-compatible
```

### 2.4 全领域最低对象与动作矩阵

| 领域 | `platform-control-plane` 最低动作 | `product-control-plane` 最低动作 |
|---|---|---|
| `content` | 读配置、灰度发布、治理策略下发、回滚、依赖读取 | 举报建单、审核、下架、恢复、推荐干预 |
| `circle` | 读配置、回滚、策略下发、依赖读取 | 圈子治理、成员处置、精选、推荐干预 |
| `chat` | 超时/轮询/重试治理、告警绑定、回滚 | 投诉建单、敏感治理、会话审计 |
| `user` | 认证链路参数治理、回滚、依赖读取 | 处罚、申诉、恢复、客服协同、双签 |
| `assistant` | 运行时参数治理、模型依赖健康、SLO 读取 | 策略切换、实验、人工审核、反馈学习 |
| `integration` | 外部依赖配置、熔断/降级、健康读取 | provider SLA 审计、故障 case、升级处理 |
| `notification` | 渠道配置、发送回滚、告警绑定 | 模板治理、活动通知策略、发送审计 |
| `recommendation` | feature store / model 依赖配置、回滚 | 实验、召回/粗排/精排运营、评估放量 |
| `realtime` | 连接参数、限流、降级、SLO 读取 | 通道治理、消息投诉、审计读取 |
| `rtc` | room/session 参数、依赖画像、回滚 | 通话治理、录制证据、申诉关联 |

## 3. 控制面与部署组合

### 3.1 支持的组合形态

设计上显式允许以下组合：
- `user-plane` 单独运行
- `user-plane + platform-control-plane` 同进程
- `user-plane + product-control-plane` 同 Pod 双容器
- `platform-control-plane + product-control-plane` 共用 `seed-box` 容器
- 三类面全部同 Pod、多容器
- 三类面全部独立 Deployment / Pod

### 3.2 当前推荐演进路径

当前阶段：
- 领域服务主容器承接 `user-plane`
- `seed-box` 作为控制面容器承接一个或两个控制面
- 同 Pod 共部署，降低运维复杂度

未来阶段：
- 用户面独立 Deployment，按用户流量 HPA
- 控制面独立 Deployment，按队列、审批 SLA、批处理 CPU、case backlog 调整
- 必要时 `platform-control-plane` 与 `product-control-plane` 再进一步拆分

### 3.3 部署元数据要求

控制面元数据必须至少描述：
- 是否可与 `user-plane` 同 Pod
- 是否必须独立 readiness / liveness
- 资源画像：`latency_sensitive` / `batch_heavy` / `audit_heavy`
- 拆分触发条件：QPS、CPU、case backlog、SLA burn、发布窗口
- 依赖类型：DB、Redis、MQ、对象存储、外部 provider

### 3.4 `control_plane.yaml` schema

```yaml
version: 1
planes:
  - domain: content
    plane: product-control-plane
    object_type: moderation_case
    route_id: product.case-detail
    surface_id: ops.portal.product.case_detail
    operations:
      - operation_id: content.case.create
        action: create
        required_scopes: [product.case.write]
        danger_level: medium
        approval_mode: none
        audit_required: true
      - operation_id: content.post.takedown
        action: takedown
        required_scopes: [product.moderation.write]
        danger_level: critical
        approval_mode: dual
        audit_required: true
    deployment_profile:
      co_locate_with_user_plane: true
      standalone_deployment_supported: true
      resource_profile: audit_heavy
      split_triggers: [case_backlog, sla_burn]
    analytics_views:
      - view_id: moderation.efficiency
        widget_types: [metric_card, line, table]
        drilldown_route_id: product.case-list
```

字段约束：
- `domain + plane + object_type` 组合唯一
- `operation_id` 必须全局唯一，命名格式：`{domain}.{object}.{action}`
- `danger_level` 只允许 `low / medium / high / critical`
- `approval_mode` 只允许 `none / single / dual`
- `audit_required=true` 时，必须存在对应 `audit_schema.yaml` 事件声明
- `analytics_views`：用于声明对象关联 dashboard 可视图，不用于定义指标计算 SQL/离线任务

### 3.5 `process_domain_mapping` 演进模型

当前文件 `deploy/shared/process_domain_mapping.yaml` 仍是 `domain -> process`。为保证三类面可独立部署，设计冻结为两阶段演进：

阶段 1：
- 保持现有 `domain -> process`
- 新增只读推导规则：`domain + plane -> process`
- 若 domain 被映射到 `seed-box`，默认表示控制面能力可由 `seed-box` 承接

阶段 2：
- 升级为显式 `domain-plane -> process`
- integration/prod 必须保持一致
- 门禁校验 domain 与 plane 是否均被唯一映射

候选格式：

```yaml
environments:
  integration:
    seed-box:
      plane_bindings:
        - domain: content
          planes: [platform-control-plane, product-control-plane]
    content-service:
      plane_bindings:
        - domain: content
          planes: [user-plane]
```

门禁影响：
- 继续保留“同一环境 domain 不能重复归属”的旧规则
- 新增“同一环境 `domain + plane` 不能重复归属”的新规则
- 新增“声明了控制面 capability 的领域，必须存在 plane binding”

## 4. 配置 schema 设计

### 4.1 `config_schema.yaml` schema

```yaml
version: 1
configs:
  - key: sys.content.http.timeout_ms
    kind: sys
    owner: platform-ops
    type: int
    default: 800
    scope: service
    reload: hot
    rollout: progressive
    risk_level: high
    ui_editable: true
    codegen_targets: [go, web]
  - key: ops.discovery.ui.home_tabs
    kind: ops
    owner: product-ops
    type: json
    default: []
    scope: audience
    reload: hot
    rollout: experiment
    risk_level: medium
    ui_editable: true
    codegen_targets: [app, web, go]
```

字段约束：
- `key` 必须以 `sys.` 或 `ops.` 开头
- `kind` 必须与 key 前缀一致
- `scope` 只允许 `global / environment / service / domain / audience / experiment`
- `rollout` 只允许 `none / progressive / experiment / package`
- `ops.*` 若作用到 App IA，必须声明 `codegen_targets` 包含 `app`
- `sys.*` 不允许声明端侧视觉布局类配置

### 4.2 运行时参数与体验参数分层

归 `ops.*`：
- 一级 tab、二级 tab、栏目顺序
- 页面布局、版式、卡片样式
- 体验类 feature flag
- 面向用户/人群/实验的 IA 配置
- dashboard 可见 widget、默认排序、默认筛选项、默认时间窗

归 `sys.*`：
- long-polling 周期
- timeout / retry / sampling / worker concurrency
- rate limit / degrade / circuit breaker
- provider timeout / queue batch size / backoff

## 5. 工作流与审计模型

### 5.1 `workflow.yaml` schema

```yaml
version: 1
workflows:
  - workflow_id: account-recovery
    object_type: recovery_case
    states:
      - requested
      - customer_service_intake
      - evidence_verified
      - dual_review
      - recovered
      - rejected
      - closed
    transitions:
      - from: requested
        to: customer_service_intake
      - from: evidence_verified
        to: dual_review
        approval_mode: dual
    sla_policy:
      first_response_minutes: 30
      resolution_minutes: 1440
    evidence_requirements:
      min_count: 1
      allowed_types: [image, video, document]
```

字段约束：
- `workflow_id` 全局唯一
- `states` 必须包含至少一个终态
- `approval_mode=dual` 的 transition 必须声明两个不同审批角色
- 需要证据的状态迁移必须有 `evidence_requirements`
- 带 SLA 的 workflow 必须声明超时事件与升级路径

### 5.2 `audit_schema.yaml` schema

```yaml
version: 1
audit_events:
  - event_id: content.post.takedown.applied
    object_type: post
    action: takedown
    required_fields:
      - actor
      - environment
      - object_ref
      - before
      - after
      - reason_code
      - request_id
    links:
      workflow: moderation-case
      evidence: optional
      release: none
```

字段约束：
- `event_id` 必须与控制面危险动作一一对应
- `required_fields` 至少包含 `actor / environment / object_ref / action / request_id`
- `before / after` 可为空，但高风险配置、处罚、恢复、回滚动作必须存在
- 若 `links.workflow` 非空，则必须能关联 `workflow_id`

### 5.3 双签与危险动作模型

强制双签动作：
- 永久封禁
- 账号恢复
- 全量配置回滚
- 生产环境高危推荐 override
- 生产环境关闭关键治理保护

危险动作最小模型：
- `action_id`
- `danger_level`
- `approval_mode`
- `confirmation_template`
- `rollback_supported`
- `required_audit_event`

## 6. codegen 设计

### 6.1 生成目标

codegen 必须统一生成：
- Web：TS types、API client、菜单 schema、表单 schema、表格列 schema、workflow 枚举、对象跳转常量、dashboard schema
- Go：handler scaffold、DTO、config schema struct、workflow 状态机骨架、审计 envelope、权限校验骨架
- Python：Pydantic model、API client、策略与事件 schema、离线校验模型
- App：IA config DTO、route/surface/page metadata、feature flag / ops config DTO

### 6.2 工具责任边界

`runtime-codegen` 负责：
- 通用 schema 校验
- Go / Python DTO 与 client/scaffold 生成
- `control_plane.yaml` / `config_schema.yaml` / `workflow.yaml` / `audit_schema.yaml` 的消费

`codegen_app_metadata` 负责：
- `ui_config.yaml`
- `portal_shell.yaml` 中与 App shell 相关的共享上下文
- `ops.*` 里的端侧 IA/flag DTO、route/surface/page 常量

现有 `codegen_ops_portal_metadata` 负责：
- `portal_shell.yaml`
- `portal_menu.yaml`
- Web TS types、route 常量、菜单树、jump rules、dashboard schema、schema renderer 输入模型

### 6.3 产物路径建议

- Web：`apps/ops-portal/src/generated/control-plane/`
- Go：`quwoquan_service/generated/control_plane/`
- Python：`quwoquan_service/services/rec-model-service/generated/control_plane/`
- App：`quwoquan_app/lib/cloud/runtime/generated/ops/`

### 6.4 codegen 不负责的内容

- 具体业务规则实现
- 风险策略计算逻辑
- 审批业务逻辑
- 算法与模型核心实现
- 页面视觉稿和交互微细节

## 7. Dashboard 口径与元数据承载

不新增第 7 类 metadata 文件，dashboard 统一复用现有 6 类对象：
- `portal_shell.yaml`
  - 承载 dashboard 全局交互默认值、时间窗、图表类型、上下文切换
- `portal_menu.yaml`
  - 承载 dashboard 入口、dashboard route、widget 编排与默认落点
- `control_plane.yaml`
  - 承载对象级 analytics view、drilldown route 与 scope
- `config_schema.yaml`
  - 承载 dashboard 布局、默认筛选、可见 widget 等 `ops.*` 配置
- `audit_schema.yaml`
  - 承载高危动作、回滚、双签等审计事件的 dashboard 数据消费边界

约束：
- 指标定义仍归领域统计口径与分析对象，不得把 dashboard 元数据当成指标真相源
- dashboard 只负责“展示、编排、路由、下钻”，不负责“计算、归因、训练”

## 8. 与现有系统/契约的对应

已存在基础：
- `contracts/configuration.md`：`sys.*` / `ops.*` 分层
- `contracts/service_governance.md`：系统治理基线
- `contracts/metadata/*/ui_config.yaml`：端侧 IA 可配置雏形
- `runtime-codegen` / `codegen_app_metadata`：已有 metadata → Go / Dart 的基础生成能力
- `platform-ops-governance` 与 `product-ops-growth`：两条领域线已存在

本节点的作用：
- 不是替代上述节点
- 而是给它们提供统一的共同上位约束与交付基线

## 9. 统一集成验收链路

统一集成验收必须覆盖以下收口项：
- 门户菜单、路由、对象跳转与权限口径一致
- `platform-ops` / `product-ops` 共享同一门户壳层与审计模型
- 各领域至少声明三类面与控制面对象视图
- 控制面元数据对象可被 Web / Go / Python / App 共同消费
- `sys.*` / `ops.*` / IaC 边界未漂移
- 部署组合从“同 Pod”切换到“独立 Pod”时无需改写契约
- 统一集成验收可纳入 `make gate-full`

### 8.1 候选校验链路

T1：
- metadata schema 校验
- route/surface/operation/object_type 唯一性校验
- `sys.*` / `ops.*` 前缀与 kind 一致性校验
- workflow 与 audit 关联完整性校验

T2：
- 门户菜单渲染
- 对象跳转可达性
- 危险动作确认与审批提示
- 全局搜索、通知、工作台入口验证
- dashboard 卡片、图表、空态、下钻与时间窗切换验证

T3：
- 各领域 plane capability 声明完整性
- Go / Python / App / Web codegen 产物存在性
- `domain-plane -> process` 映射完整性
- `seed-box` 同 Pod 与独立 Pod 契约一致性

T4：
- 生产前统一门户冒烟
- 典型高危动作审计回放
- 账号恢复双签链路
- 推荐 override 灰度与回滚链路
- 核心 dashboard 在 integration/prod 样式语义与数据下钻一致性验证

### 8.2 `make gate-full` 候选接入

建议新增以下候选校验：
- `verify-control-plane-metadata`
- `verify-portal-menu-unique`
- `verify-domain-plane-binding`
- `verify-config-boundary`
- `verify-workflow-audit-link`
- `verify-codegen-control-plane-targets`
- `verify-dashboard-schema-link`

## 10. 适用场景与约束

适用场景：
- 多领域、多控制面、全栈共担的单仓体系
- 需要短期快速落地、长期可拆分演进的控制面架构
- 需要 metadata-first 与 codegen-first 的控制面交付模式

约束与局限：
- 本节点冻结的是共同上位规格，不替代各领域对象的最终字段设计
- 门户前端虽然冻结为 React + TypeScript，但具体组件库仍由下游节点决定
- `process_domain_mapping.yaml` 的正式结构升级需要后续落库实现
- dashboard 图表引擎与数仓实现仍由下游节点决定，但元数据边界已冻结

## 11. 未来演进

目标态：
- 统一门户壳层稳定
- 控制面元数据对象成为一级真相源
- plane 级部署映射可验证
- Web / Go / Python / App 四端契约自动同步

未来演进方向：
- 从当前 `domain -> process` 扩展到 `domain-plane -> process`
- 从单前端域模块化演进到可插拔模块体系
- 从 IA config 扩展到完整的 app shell / route / surface metadata single source
- 将统一集成验收接入 `make gate-full`
