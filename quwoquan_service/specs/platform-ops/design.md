# platform-ops 设计方案

## 设计动因

`platform-ops` 需要作为统一研发自助平台，承接所有领域服务的：
- 服务目录
- 配置中心
- 治理策略
- 发布灰度
- 环境与依赖
- 可观测与 SLO
- Runbook
- CI/CD 门禁

当前若不做统一设计，会出现以下问题：
- 各领域各自维护 `sys.*` 配置项与灰度口径
- 治理策略模板、告警模板、发布回滚和审计分散在多个实现里
- 控制面接口各自手写，无法统一 codegen
- 门户菜单、对象模型与后端契约容易出现第二真相源
- 当前 `seed-box` 同 Pod 的部署便利会反向污染契约，导致未来拆 Pod 返工

## 上游输入评审

### spec 评审

当前 `spec.md` 已明确：
- `platform-ops` 的产品范围
- 与 `product-ops` 的严格边界
- 三类面架构与部署任意组合要求
- `sys.*` / `ops.*` / IaC 分层
- 控制面元数据对象与 codegen 方向

结论：
- `spec.md` 足以支撑本轮设计。

### acceptance 评审

当前 `acceptance.yaml` 已覆盖：
- 平台能力范围
- 边界分层
- 三类面独立与部署演进
- 配置/治理/灰度/审计
- codegen 与元数据要求

结论：
- `acceptance.yaml` 可测且稳定，足以进入 `/design`。

### 仍需在设计中补全的内容
- 字段级对象模型
- 元数据 schema 草案
- 门户风格与当前 App 语义风格对齐方案
- codegen 分工与路径
- plane 级部署映射演进

## 对标输入分析

### 对标对象
- `Backstage + Argo Rollouts`
- `Sentinel / Service Mesh` 的治理策略思路
- `Datadog / Grafana` 类仪表盘与运维工作台体验

### 借鉴点
- 统一入口、统一目录、统一环境上下文
- 配置与发布版本化，而不是操作“当前线上状态”
- 治理策略模板化、可审计、可回滚
- Dashboard / SLO / 告警 / Runbook 统一闭环
- 危险动作必须强确认、可审批、可追溯

### 不借鉴点
- 不引入过重的 mesh-first 架构
- 不引入过多独立微服务
- 不让控制台直接成为唯一真相源

### 适用边界
- 适合当前“全栈团队 + 单仓 + metadata-first + codegen-first”的组织与工程模式
- 不适合一开始就按大型平台团队拆成大量独立平台服务

### 当前差距
- 门户壳层未落地
- 控制面元数据 schema 已有首版生成链路，但 contract test 与门禁尚未补齐
- plane 级部署映射尚未接入门禁
- 仪表盘、配置 diff、灰度面板仍未实现

## 方案对比

### 方案 A：单体门户 + 单体后端 + 纯实时配置变更

**优点**：
- 实现最快
- 认知成本最低

**缺点**：
- 高风险配置缺乏版本化灰度保障
- worker 型任务会与在线控制请求互相影响
- 容易把门户 UI、配置中心、脚本状态混成一套临时真相源

**适用条件**：
- 极小规模原型阶段

### 方案 B：统一门户 + 模块化单体后端 + 配置包版本化为主、动态刷新为辅

**优点**：
- 保留单一平台边界，适合当前团队
- 能同时支撑在线控制 API 与后台任务
- 高风险配置有版本、灰度、回滚与审计
- 易于与现有 `runtime-config`、`runtime-governance`、`runtime-codegen` 衔接

**缺点**：
- 比简单单体多一层 worker 与阶段门禁设计
- 需要提前把 metadata schema 设计清楚

**适用条件**：
- 当前阶段最适合

### 方案 C：统一门户 + 多服务平台后端 + plane 级独立调度

**优点**：
- 长期演进空间最大
- 组件边界清晰

**缺点**：
- 对当前团队过重
- 服务发现、鉴权、调度与审计复杂度显著上升

**适用条件**：
- 大规模平台团队或明显超出当前容量后再考虑

## 选型决策

**选定方案**：方案 B

**理由**：
- 与当前“全栈研发自助平台”的团队模式最匹配
- 与现有单仓、runtime-first、metadata-first 体系兼容
- 能在不引入过高复杂度的前提下，支撑配置治理、灰度回滚、审计、仪表盘、后台任务
- 能支持短期 `seed-box` 同 Pod、长期独立 Deployment 的演进路线

## 关键设计决策

- 决策 1：门户采用统一 Web 门户 `ops-portal`，不拆成两个独立站点。
- 决策 2：门户前端冻结为 `React + TypeScript`。
- 决策 3：门户体验风格必须与当前 App 的语义风格一致，采用同一套“语义标签优先、禁止魔法值、对象/动作语义稳定”的设计语言。
- 决策 4：后端采用模块化单体 `platform-ops` + 后台 worker。
- 决策 5：高风险配置默认走“配置包版本化 + 渐进灰度 + 可回滚”，低风险配置才允许热刷新。
- 决策 6：控制面元数据作为唯一真相源，优先生成 Web / Go / Python 契约，后续再接 App 只读消费。
- 决策 7：部署模型目标态升级为 `domain-plane -> process`，短期兼容现有 `domain -> process`。
- 决策 8：平台仪表盘是一级能力，不是附属页面。

## 门户风格与语义风格对齐

### 总体原则

门户虽然是 Web 控制台，但视觉与交互语义必须与当前 App 保持一致：
- 用统一的语义颜色、状态颜色、危险动作颜色
- 用统一的对象命名方式，不以临时文案或运营昵称驱动逻辑
- 用统一的页面层级与导航语义
- 仪表盘、列表、详情、审批、diff 页面都要统一“对象 -> 状态 -> 动作 -> 审计”的阅读顺序

### 门户风格基线

- 首页：卡片化总览 + 重点状态 + 待办工作台
- 列表页：高密度表格 + 过滤器 + 环境切换 + 快速对象跳转
- 详情页：对象头部摘要 + 当前状态 + 配置/依赖/审计/事件时间线
- 仪表盘：趋势图、分布图、阶段状态、SLO 预算消耗、灰度进度
- 危险动作：固定危险区、二次确认、审批链、回滚入口、审计提示

### 交互要求

- 所有危险动作必须固定展示风险级别、影响面、回滚入口
- 配置 diff 默认显示“旧值 / 新值 / 风险说明 / 生效范围 / 发布时间窗”
- 发布灰度默认显示“5 / 25 / 50 / 100”阶段、观察窗口、门禁状态
- 仪表盘必须支持从总体趋势下钻到服务、环境、plane 与对象详情

## 对象模型

### 配置中心对象

| 对象 | 字段重点 | 说明 |
|---|---|---|
| `ConfigSchema` | `key`, `owner`, `description`, `type`, `default`, `scope`, `reload`, `rollout`, `riskLevel`, `secret` | 配置项定义 |
| `ConfigValueSet` | `schemaKey`, `environment`, `service`, `value`, `source`, `versionRef` | 生效值视图 |
| `ConfigPackage` | `packageId`, `version`, `environment`, `serviceSet`, `items`, `summary` | 配置包快照 |
| `ConfigDiff` | `beforeVersion`, `afterVersion`, `changedKeys`, `riskSummary` | 版本 diff |
| `ConfigRelease` | `releaseId`, `packageVersion`, `phase`, `status`, `window`, `metrics` | 发布执行对象 |

### 治理策略对象

| 对象 | 字段重点 | 说明 |
|---|---|---|
| `GovernancePolicyTemplate` | `policyId`, `policyType`, `defaults`, `riskLevel`, `supportedPlanes` | 策略模板 |
| `GovernancePolicyBinding` | `policyId`, `service`, `plane`, `overrideSet`, `version` | 服务绑定 |
| `RiskApprovalRecord` | `approvalId`, `targetRef`, `riskLevel`, `approvers`, `decision` | 风险审批 |

### 发布灰度对象

| 对象 | 字段重点 | 说明 |
|---|---|---|
| `RolloutPlan` | `planId`, `targetType`, `stages`, `gateRules`, `rollbackPlan` | 灰度计划 |
| `RolloutStage` | `stageId`, `percentage`, `window`, `checks` | 单阶段 |
| `RollbackRecord` | `rollbackId`, `releaseId`, `trigger`, `operator`, `result` | 回滚记录 |

### 环境与依赖对象

| 对象 | 字段重点 | 说明 |
|---|---|---|
| `EnvironmentTopology` | `environment`, `planeBindings`, `releaseChannel` | 环境拓扑 |
| `PlaneBinding` | `domain`, `plane`, `process`, `container`, `scalingMode` | plane 绑定 |
| `DependencyProfile` | `service`, `dependencyType`, `endpoint`, `criticality`, `health` | 依赖画像 |
| `CapacityProfile` | `service`, `plane`, `resourceClass`, `hpaPolicy`, `splitTrigger` | 资源画像 |

### 仪表盘与可观测对象

| 对象 | 字段重点 | 说明 |
|---|---|---|
| `SLOPolicy` | `sloId`, `service`, `plane`, `indicator`, `objective`, `burnRules` | SLO 规则 |
| `AlertTemplate` | `templateId`, `signal`, `threshold`, `severity`, `runbookRef` | 告警模板 |
| `DashboardCard` | `cardId`, `metricRef`, `trend`, `status`, `drilldownTarget` | 仪表盘卡片 |
| `DashboardSlice` | `dimension`, `filterSet`, `chartType`, `timeRange` | 仪表盘切片 |
| `GateRule` | `gateId`, `stage`, `checks`, `blocking`, `auditMode` | 门禁规则 |
| `Runbook` | `runbookId`, `triggerType`, `steps`, `rollbackHints` | 运维手册 |
| `AuditRecord` | `auditId`, `actor`, `environment`, `objectRef`, `action`, `before`, `after` | 审计记录 |

## 门户菜单模型

### 一级菜单
- `服务目录`
- `配置中心`
- `治理策略`
- `发布灰度`
- `环境与依赖`
- `可观测与 SLO`
- `Runbook 与演练`
- `CI/CD 门禁`

### 二级菜单建议

#### `服务目录`
- 服务清单
- 领域/plane 绑定
- 依赖拓扑
- owner 与责任边界

#### `配置中心`
- 配置项列表
- 配置包
- 版本 diff
- 发布记录
- 回滚记录

#### `治理策略`
- 超时策略
- 重试策略
- 熔断策略
- 限流策略
- 降级策略
- 健康策略

#### `发布灰度`
- 当前灰度
- 阶段门禁
- 灰度审计
- 回滚入口

#### `环境与依赖`
- 环境矩阵
- plane 拓扑
- DB / Redis / MQ / HTTP 依赖
- 容量画像

#### `可观测与 SLO`
- 总览仪表盘
- 服务仪表盘
- SLO / error budget
- 告警模板
- 事件时间线

#### `Runbook 与演练`
- runbook 列表
- 演练计划
- 演练记录

#### `CI/CD 门禁`
- 门禁规则
- 失败记录
- 放行记录

## 元数据唯一源分层

### `portal_shell.yaml`
承载：
- 门户级环境切换
- 全局搜索类型
- 全局通知类型
- 工作台视图
- 全局上下文切换器

### `portal_menu.yaml`
承载：
- 一级/二级菜单
- 路由
- 权限
- 默认落点
- 对象跳转关系

### `control_plane.yaml`
承载：
- `platform-control-plane` 的对象类型、路由、动作、危险级别、审计要求、部署属性

### `config_schema.yaml`
承载：
- `sys.*` 配置定义
- scope / reload / rollout / risk_level
- codegen 目标

### `audit_schema.yaml`
承载：
- 高风险动作审计结构
- old/new value
- 审批、发布、回滚与对象关联

### 代码禁止维护的第二真相源
- 禁止前端手写菜单结构作为唯一菜单定义
- 禁止服务端手写控制面 DTO 作为唯一 schema
- 禁止 Python 与 Go 分别维护独立控制面字段命名
- 禁止将 `sys.*` 范围写死在业务代码 switch/case 中

## 元数据基线执行

本轮 `/design` 新增共享元数据骨架：
- `contracts/metadata/_shared/portal_shell.yaml`
- `contracts/metadata/_shared/portal_menu.yaml`
- `contracts/metadata/_shared/control_plane.yaml`
- `contracts/metadata/_shared/config_schema.yaml`
- `contracts/metadata/_shared/workflow.yaml`
- `contracts/metadata/_shared/audit_schema.yaml`

这些文件作为统一控制面 metadata baseline，当前先定义结构与命名语义，后续由 codegen 逐步接入。

## codegen 分工

### `runtime-codegen`
负责：
- Go DTO / handler scaffold
- Python schema / client
- 通用 metadata 校验

### `codegen_app_metadata`
负责：
- App 侧只读消费的 route / IA / flag / 常量

### `codegen_ops_portal_metadata`
现有工具负责：
- TS types
- 菜单 schema
- 对象详情与表格 schema
- Dashboard schema
- workflow / audit 枚举
- API client

## TDD / ATDD 策略

- ATDD：先冻结 `spec.md + acceptance.yaml`
- TDD：
  - 先写 metadata / schema contract tests
  - 再写 codegen 产物测试
  - 再写门户与平台后端集成测试
  - 最后补灰度、回滚、仪表盘、门禁与部署组合验证

## Story 与测试层映射

- Story 1：配置中心对象模型与 schema
  - T1：metadata contract
  - T3：发布/回滚集成验证
- Story 2：治理策略模型
  - T1：schema contract
  - T3：策略绑定与 fallback 验证
- Story 3：发布灰度模型
  - T1：metadata contract
  - T3：阶段门禁与回滚流程
  - T4：真实灰度演练
- Story 4：环境与依赖模型
  - T1：部署映射 contract
  - T3：plane 绑定与依赖探测
- Story 5：门户与仪表盘
  - T2：门户 UI / 交互
  - T3：门户与后端对象模型联调

## 角色职责与多重防护网

- 产品：定义平台入口、对象边界、研发自助体验
- 架构：定义三类面、元数据 schema、部署演进与 codegen 责任
- 开发：落 metadata、codegen、后端 API、门户页面、worker 与测试
- 测试：验证 schema、灰度、回滚、仪表盘、门禁、部署组合
- 发布：验证配置包、灰度阶段、回滚阈值与放行策略

## 实时性与弱网设计

本平台不是实时社交主链路，但仍需定义：
- 门户读取对象默认秒级到十秒级刷新即可
- 配置高风险变更以版本发布为主，不追求“秒级线上热切”
- 仪表盘允许分钟级聚合延迟，但告警与回滚触发必须具备及时性
- 门户前端弱网场景下需支持只读降级、分页加载、延迟容忍与重试

## 并发性能与容量设计

- 在线控制 API 为中低频请求
- 配置 diff、依赖探测、SLO 预算计算、审计归集放到 worker
- 用户面和控制面资源画像必须分开
- 仪表盘查询需按时间窗、对象、环境切片缓存，避免重查询直接打后端核心服务

## 灰度发布与回滚设计

- 默认阶段：`5% -> 25% -> 50% -> 100%`
- 每阶段必须绑定观察窗口与门禁检查
- 指标异常自动停止并触发回滚建议
- 高风险配置不得在实例内直接切换“current”，而必须通过版本与实例组绑定

## 未来演进

- 演进点 1：将 `domain -> process` 门禁升级为 `domain-plane -> process`
- 演进点 2：补齐 `codegen_ops_portal_metadata` 的 contract tests、schema 覆盖面与门户消费页面
- 演进点 3：将统一平台控制面验收接入 `make gate-full`
- 演进点 4：将仪表盘 schema 也纳入 metadata-first

## 存量带规划任务

- 低风险热更新配置的最终名单仍需在 `/dev` 前明确
- `codegen_ops_portal_metadata` 的生成物覆盖面仍需扩展到更多对象详情与 dashboard 场景
- 仪表盘组件库与图表渲染库选择留待实现前冻结
