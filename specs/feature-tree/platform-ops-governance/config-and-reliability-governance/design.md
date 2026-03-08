# Design：config-and-reliability-governance

## 设计动因

本节点负责把 `platform-ops` PRD 中“配置中心、治理策略、发布灰度、环境与依赖”四类平台能力下沉为可设计的实现模型。若不在本节点统一，会出现：
- 各领域各自维护 `sys.*` 配置读写与灰度口径
- 治理策略模板与服务覆盖关系分散实现
- 配置发布、回滚、依赖状态、门禁审计各自建模
- 控制面元数据与 codegen 目标失去统一入口

## 上游评审结论

当前 `platform-ops/spec.md` 与本节点 `spec.md / acceptance.yaml / tasks.md` 已足以支撑进入下一轮 `/design`。  
本节点后续详细设计需重点回答：
- 配置包模型与发布模型
- 治理策略模板与服务覆盖模型
- 依赖画像与环境差异模型
- `control_plane.yaml` / `config_schema.yaml` 字段级 schema
- plane 级部署与 `seed-box` 演进模型

## 方案比较与结论

### 1. 配置发布模型

#### 方案 A：配置包版本 + 渐进灰度

优点：
- 高风险配置天然可审计、可回滚
- 与 `CONFIG_VERSION` / 实例组绑定一致，便于发布与回滚
- 最适合超时、重试、熔断、限流、采样率、依赖连接参数等系统级配置

缺点：
- 低风险参数调整较慢
- 对配置中心的“秒级生效”能力利用不足

#### 方案 B：实时动态配置变更

优点：
- 低延迟生效
- 适合低风险、观测类或调试类参数

缺点：
- 高风险配置容易绕开灰度实例组
- 回滚与审计链更复杂
- 容易形成“线上 current 状态”而非版本真相源

#### 方案 C：混合模式

规则：
- 高风险配置：配置包版本 + 渐进灰度
- 低风险可热更新配置：配置中心动态刷新
- 仍要求统一审计与版本快照

结论：
- 选择 **方案 C**。
- 其中高风险配置必须默认走 **方案 A**；低风险热更新只是补充能力，不能成为主路径。

### 2. 控制面后端组织方式

#### 方案 A：单体 `platform-ops`

优点：
- 上手快
- 小团队维护成本最低

缺点：
- 审计、灰度、配置 diff、依赖探测、告警同步等后台任务会挤压在线请求
- 后续拆 worker 返工概率高

#### 方案 B：模块化单体 + 后台 worker

优点：
- 保持单一服务心智
- 将“查询 / 控制 API”与“探测 / 对账 / 审计归集 / 灰度阶段任务”分开
- 非常适合当前“全栈团队自助运维”模式

缺点：
- 比纯单体多一层任务调度与状态同步

#### 方案 C：多服务拆分

优点：
- 理论边界最清晰
- 大规模演进空间最大

缺点：
- 当前阶段组织与工程复杂度过高
- 需要额外网关、鉴权与分布式调度治理

结论：
- 选择 **方案 B：模块化单体 + 后台 worker**。
- 第一阶段保留单一 `platform-ops` 服务边界，但内部拆分在线控制 API 与异步 worker。

### 3. 部署映射模型

#### 方案 A：继续维持 `domain -> process`

优点：
- 兼容当前已有部署文件
- 改动最小

缺点：
- 无法表达三类面拆分
- 无法为后续独立 control-plane 提供门禁

#### 方案 B：升级到 `domain-plane -> process`

优点：
- 能表达 `user-plane` / `platform-control-plane` / `product-control-plane`
- 能约束任意部署组合
- 能天然支持 `seed-box` 过渡期与独立 Pod 目标态

缺点：
- 需要扩展现有 `process_domain_mapping` 与验证脚本

结论：
- 目标态选择 **方案 B**
- 落地路径采用“兼容迁移”：
  - 短期继续兼容 `domain -> process`
  - 设计与 codegen 先全面采用 `domain-plane -> process`
  - 门禁逐步升级

### 4. codegen 路径

#### 方案 A：全量塞入 `runtime-codegen`

优点：
- 入口统一

缺点：
- Go 代码生成与门户 TS / App metadata 生成耦合过高

#### 方案 B：扩展现有工具链

分工：
- `runtime-codegen`：Go / Python / 通用 schema
- `codegen_app_metadata`：App 端 metadata
- 新增 `codegen_ops_portal_metadata`：门户 TS schema

优点：
- 与当前工程最契合
- 责任清晰
- 可渐进演进

缺点：
- 需要多工具之间约定统一输入 schema

#### 方案 C：重写单一控制面生成器

优点：
- 理论上模型最干净

缺点：
- 重复建设，且会和现有工具链冲突

结论：
- 选择 **方案 B**。

## 适用场景与约束

- **适用**：面向统一研发自助平台、统一 `sys.*` 配置治理、统一治理策略与统一发布灰度的平台控制面建设。
- **约束**：与 `platform-ops` 服务级规格、`runtime-control-plane-foundation` 共同上位规格及 `contracts/configuration.md` 保持一致。
- **局限性**：当前文档仍是设计入口，不替代字段级 schema、流程图、时序图与 codegen 模板细节。

## 最终设计

### 1. 总体架构

`platform-ops` 采用“统一门户 + 单服务边界 + 模块化单体 + 后台 worker”的架构：
- `ops-portal`
  - 统一壳层、统一环境上下文、统一搜索、统一通知、统一审计入口
- `platform-ops api`
  - 对外提供配置、治理、发布、依赖、SLO、runbook、gate 等控制面接口
- `platform-ops worker`
  - 负责依赖探测、发布阶段检查、SLO 预算计算、配置对账、审计归集、告警同步
- `runtime-config` / `runtime-governance` / `runtime-observability`
  - 作为各领域服务真正消费的运行时能力

### 2. 对象模型

#### 2.1 配置中心对象

| 对象 | 关键字段 | 说明 |
|---|---|---|
| `ConfigSchema` | `key`, `owner`, `type`, `default`, `scope`, `reload`, `rollout`, `riskLevel`, `secret` | 配置项定义，唯一真相在 metadata |
| `ConfigValueSet` | `schemaKey`, `environment`, `service`, `value`, `source`, `versionRef` | 某环境/服务上的生效值视图 |
| `ConfigPackage` | `packageId`, `version`, `environment`, `serviceSet`, `items`, `summary` | 一次配置发布的包快照 |
| `ConfigDiff` | `beforeVersion`, `afterVersion`, `changedKeys`, `riskSummary` | 版本差异视图 |
| `ConfigRelease` | `releaseId`, `packageVersion`, `phase`, `status`, `window`, `metrics` | 发布执行对象 |

#### 2.2 治理策略对象

| 对象 | 关键字段 | 说明 |
|---|---|---|
| `GovernancePolicyTemplate` | `policyId`, `policyType`, `defaults`, `riskLevel`, `supportedPlanes` | timeout/retry/circuit/rate-limit/degrade/health 模板 |
| `GovernancePolicyBinding` | `policyId`, `service`, `plane`, `overrideSet`, `version` | 模板绑定到具体服务/plane 的覆盖 |
| `RiskApprovalRecord` | `approvalId`, `targetRef`, `riskLevel`, `approvers`, `decision` | 高风险动作审批记录 |

#### 2.3 发布灰度对象

| 对象 | 关键字段 | 说明 |
|---|---|---|
| `RolloutPlan` | `planId`, `targetType`, `stages`, `gateRules`, `rollbackPlan` | 配置/治理发布计划 |
| `RolloutStage` | `stageId`, `percentage`, `window`, `checks` | 5%/25%/50%/100% 阶段 |
| `RollbackRecord` | `rollbackId`, `releaseId`, `trigger`, `operator`, `result` | 回滚记录 |

#### 2.4 环境与依赖对象

| 对象 | 关键字段 | 说明 |
|---|---|---|
| `EnvironmentTopology` | `environment`, `planeBindings`, `releaseChannel` | 环境视角的 plane/process 绑定 |
| `PlaneBinding` | `domain`, `plane`, `process`, `container`, `scalingMode` | 三类面到进程/容器的映射 |
| `DependencyProfile` | `service`, `dependencyType`, `endpoint`, `criticality`, `health` | DB/Redis/MQ/HTTP 下游依赖画像 |
| `CapacityProfile` | `service`, `plane`, `resourceClass`, `hpaPolicy`, `splitTrigger` | 弹性与拆分画像 |

#### 2.5 可观测与门禁对象

| 对象 | 关键字段 | 说明 |
|---|---|---|
| `SLOPolicy` | `sloId`, `service`, `plane`, `indicator`, `objective`, `burnRules` | SLO 与预算门禁 |
| `AlertTemplate` | `templateId`, `signal`, `threshold`, `severity`, `runbookRef` | 告警模板 |
| `GateRule` | `gateId`, `stage`, `checks`, `blocking`, `auditMode` | CI/CD 与发布门禁 |
| `Runbook` | `runbookId`, `triggerType`, `steps`, `rollbackHints` | 运维处置手册 |

### 3. 元数据 schema 设计

#### 3.1 `control_plane.yaml`

用途：
- 描述 `platform-control-plane` 路由、对象、危险动作、部署属性

建议结构：

```yaml
version: 1
domain: content
planes:
  - plane: platform-control-plane
    object_type: ConfigSchema
    routes:
      - method: GET
        path: /internal/platform/config-schemas
        operation: ListConfigSchemas
        required_scopes: [platform_ops.read]
        danger_level: low
        audit_required: false
    deployment_profile:
      co_locatable_with_user_plane: true
      resource_class: audit_heavy
      split_triggers: [cpu, backlog, slo_burn]
```

#### 3.2 `config_schema.yaml`

用途：
- 描述 `sys.*` 配置定义与发布属性

建议结构：

```yaml
version: 1
configs:
  - key: sys.chat.long_poll.interval_ms
    owner: chat-team
    description: client long polling interval
    type: int
    default: 3000
    scope: service
    reload: hot
    rollout:
      mode: package_gray
      stages: [5, 25, 50, 100]
    risk_level: high
    secret: false
    codegen_targets: [go, python, web]
```

#### 3.3 `portal_menu.yaml`

用途：
- 描述 `Platform Ops` 菜单与权限

建议结构：

```yaml
version: 1
menus:
  - menu_id: platform.config-center
    parent_menu_id: platform
    route_id: platform_config_center
    required_scope: platform_ops.config.read
    environment_aware: true
    object_types: [ConfigSchema, ConfigPackage, ConfigRelease]
```

#### 3.4 `audit_schema.yaml`

用途：
- 描述高风险动作审计事件

建议结构：

```yaml
version: 1
audit_events:
  - action: config.release.rollback
    required_fields:
      - actor
      - target
      - environment
      - release_id
      - before
      - after
      - approval_record
```

### 4. codegen 分工

#### 4.1 `runtime-codegen`

负责：
- Go DTO / handler scaffold
- Python schema / client
- 通用 metadata 校验

#### 4.2 `codegen_app_metadata`

负责：
- App 端仅与控制面相关的消费常量与配置 DTO
- 仅消费与 App 有关的 schema，不承载平台后台页面模型

#### 4.3 `codegen_ops_portal_metadata`

现有工具负责：
- 生成 TS types
- 生成菜单 schema
- 生成对象详情 / 列表列 / 表单 schema
- 生成 workflow / audit 枚举与 client

### 5. 部署演进设计

#### 当前阶段
- 允许 `seed-box` 与领域处置服务同 Pod
- `platform-control-plane` 可以和 `product-control-plane` 共用控制面容器
- 用户面保持主服务容器，控制面流量不对 App 直接暴露

#### 目标阶段
- `user-plane` 独立 Deployment
- `platform-control-plane` 独立 Deployment
- `product-control-plane` 独立 Deployment 或与 `platform-control-plane` 分离

#### 演进约束
- 契约不依赖当前部署形态
- 进程编排变化不得改动控制面 API 语义
- 配置包、发布版本、审计记录必须跨部署形态保持连续

### 6. 与下游节点的分工

本节点负责总体模型，下游节点负责专项深入：
- `config-source-governance/risky-config-gray-release`
  - 负责高风险配置灰度与回滚细节
- `reliability-policy-control/timeout-retry-circuit-ratelimit-degrade`
  - 负责治理策略细节
- `observability-and-alerting/slo-error-budget-governance`
  - 负责 SLO 与预算治理细节
- `runtime-config/config-provider-layering`
  - 负责运行时配置消费与 provider 细节

## 未来演进

- 细化对象模型：`ConfigSchema`、`ConfigPackage`、`ConfigRelease`、`GovernancePolicy`、`DependencyProfile`、`SLOPolicy`
- 细化 plane 级部署与门禁校验
- 将统一验收链路纳入 `make gate-full`
