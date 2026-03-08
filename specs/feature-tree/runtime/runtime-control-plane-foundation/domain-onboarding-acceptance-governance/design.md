# Design：domain-onboarding-acceptance-governance

## 设计动因

本节点的设计目标不是“在本轮 `/design` 中直接完成所有领域的控制面接入实现”，而是把后续在**同一 `/dev` 会话中统一推进所有领域接入**所需要的**唯一上位设计基线**冻结下来。执行策略调整为：先完成一个模板域，再在同一会话内复制到所有领域，最终仍由本节点做集中验收。

因此，本节点的设计必须同时回答 5 个问题：

1. `domain_onboarding` 元数据究竟长什么样
2. 各领域 `<domain>.yaml` 如何低成本声明自身接入状态
3. verify / codegen / gate / deploy 如何共同消费该元数据
4. 部署拓扑如何从 `domain -> process` 演进到 `domain-plane -> process`
5. 最终集中验收如何自动聚合，而不是人工逐域对表

## 上游评审结论

当前 `spec.md` 与 `acceptance.yaml` 已足以进入设计，原因如下：

- 已明确 `domain_onboarding` 作为统一接入真相源
- 已冻结领域最小接入包与统一实施/集中验收职责边界
- 已明确命令、规则、gate 与 deploy 都要围绕该真相源演进
- 已明确最终集中验收不允许退化为人工对表

本轮 `/design` 需要补齐的是：

- 字段级 schema
- 分领域实例模板
- gate 聚合模型
- plane-aware deployment binding
- 最终集中验收状态机
- 全领域接入现状矩阵与统一实施批次

## 方案对比

### 方案 A：只在文档里维护接入矩阵

做法：

- 在 `spec.md` / `design.md` 中维护一张领域表
- 各领域按文档约定自行补代码和测试
- 最终人工比对是否完成

优点：

- 实施快
- 不需要新增 metadata schema

缺点：

- 无法被 verify / codegen / gate / portal 消费
- 并行会话极易口径漂移
- 最终集中验收仍然依赖人工

结论：

- 不选。违反 metadata-first，也无法支撑低代码标准接入。

### 方案 B：以 `domain_onboarding` metadata 作为统一真相源

做法：

- 新增 `domain_onboarding_schema.yaml`
- 每个领域维护独立的 `domains/<domain>.yaml`
- verify / codegen / gate / deploy / portal 共同消费该元数据

优点：

- 每个领域独立维护，适合在同一会话中串行复制接入
- 容易形成统一状态聚合
- 接入成本主要是补 metadata 与测试资产，不是重写业务
- 可自然演进到门户状态面板与统一验收面板

缺点：

- 需要新增 schema、校验与聚合逻辑
- 需要梳理与现有 `service.yaml` / `control_plane.yaml` / `workflow.yaml` 的关系

结论：

- 选择此方案。

## 关键决策

### 1. 真相源结构

接入矩阵采用“两层真相源”：

- 全局 schema：
  - `quwoquan_service/contracts/metadata/_control_plane/domain_onboarding_schema.yaml`
- 分领域实例：
  - `quwoquan_service/contracts/metadata/_control_plane/domains/<domain>.yaml`

原因：

- 避免所有领域同时编辑一个大文件
- 每个领域只需维护自己的接入状态
- 全局工具链可统一聚合

### 2. `domain_onboarding_schema.yaml` 设计

推荐结构：

```yaml
version: 1
schema_id: domain-onboarding
status_enum:
  - draft
  - schema_frozen
  - metadata_ready
  - generated
  - minimum_test_ready
  - deploy_binding_ready
  - final_acceptance_ready
  - accepted
required_sections:
  - identity
  - service_ownership
  - plane_contracts
  - object_bindings
  - metadata_bindings
  - codegen_targets
  - quality_gates
  - deployment_binding
  - portal_projection
  - final_acceptance
```

字段设计采用 10 个逻辑段：

1. `identity`
   - `domain`
   - `display_name`
   - `bounded_context`
2. `service_ownership`
   - `owner_service`
   - `metadata_domains`
   - `primary_entities`
3. `plane_contracts`
   - `user_plane`
   - `platform_control_plane`
   - `product_control_plane`
4. `object_bindings`
   - 各 plane 的 `object_types`
   - 最低动作集
   - danger / approval / audit
5. `metadata_bindings`
   - 引用的 `service.yaml`
   - 引用的 `control_plane.yaml`
   - 引用的 `workflow.yaml`
   - 引用的 `audit_schema.yaml`
   - 引用的 `tests/e2e.yaml`
6. `codegen_targets`
   - `web`
   - `go`
   - `python`
   - `app`
7. `quality_gates`
   - `required_test_layers`
   - `required_gate_levels`
   - `required_acceptance_files`
8. `deployment_binding`
   - `deployment_profile`
   - `recommended_container_mode`
   - `supports_independent_scaling`
   - `plane_binding_source`
9. `portal_projection`
   - `menu_surfaces`
   - `search_types`
   - `audit_views`
   - `dashboard_views`
10. `final_acceptance`
   - `acceptance_status`
   - `blocking_gaps`
   - `evidence_refs`

### 3. `domains/<domain>.yaml` 模板

每个领域实例采用统一模板。推荐结构如下：

```yaml
version: 1
domain: content
display_name: Content
owner_service: content-service
metadata_domains: [content]
primary_entities:
  - post
  - report

planes:
  user-plane:
    enabled: true
    object_types: [feed, post, comment, media]
    minimum_actions: [list_feed, get_post, create_post, create_comment]
  platform-control-plane:
    enabled: true
    object_types: [service_object, config_object, governance_object, audit_record]
    minimum_actions: [read_config, apply_governance, release_config, rollback_config]
  product-control-plane:
    enabled: true
    object_types: [moderation_case, recommendation_policy, analytics_object]
    minimum_actions: [submit_case, takedown, restore, recommendation_override]

danger_actions:
  - takedown
  - rollback_config
approval_modes:
  takedown: dual
  rollback_config: dual
audit_events:
  - content.post.takedown_applied
  - content.config.rollback_applied

metadata_bindings:
  service_contracts:
    - contracts/metadata/content/post/service.yaml
    - contracts/metadata/content/report/service.yaml
  e2e_contracts:
    - contracts/metadata/content/post/tests/e2e.yaml
  control_plane_contracts:
    platform:
      object_types: [service_config, config_release]
    product:
      object_types: [moderation_case]

codegen_targets:
  web: required
  go: required
  python: optional
  app: required

required_test_layers:
  T1: required
  T2: required
  T3: required
  T4: required

deployment_binding:
  profile: seed-box-compatible
  plane_binding_source: deploy/shared/process_domain_plane_mapping.yaml

portal_projection:
  search_types: [post, moderation_case, config_release]
  dashboard_views: [product-dashboard, platform-dashboard]

acceptance_status: ready_for_parallel_dev
blocking_gaps: []
evidence_refs: []
```

### 4. 与现有 metadata 的关系

`domain_onboarding` 不取代现有 metadata，而是作为“统一接入声明层”。

关系如下：

- `service.yaml`
  - 继续定义用户面 / 对外业务 API 契约
- `_control_plane/platform/control_plane.yaml`
  - 继续定义平台控制面的对象与动作 schema
- `_control_plane/product/control_plane.yaml`
  - 继续定义产品控制面的对象与动作 schema
- `workflow.yaml`
  - 继续定义治理/恢复/实验等状态机
- `audit_schema.yaml`
  - 继续定义审计记录模型
- `domain_onboarding`
  - 负责声明“某个领域是否已经把这些东西接齐”

因此：

- `service.yaml` 等是“领域能力契约”
- `domain_onboarding` 是“领域接入完成度契约”

### 5. 接入状态机

领域接入状态采用固定状态机，供 gate、portal 和集中验收共同消费。

```text
draft
  -> schema_frozen
  -> metadata_ready
  -> generated
  -> minimum_test_ready
  -> deploy_binding_ready
  -> final_acceptance_ready
  -> accepted
```

状态语义：

- `draft`
  - 仅建立领域接入意图
- `schema_frozen`
  - `<domain>.yaml` 已存在且通过基本 schema 校验
- `metadata_ready`
  - `service/e2e/control_plane/workflow/audit` 引用完整
- `generated`
  - codegen 产物齐全
- `minimum_test_ready`
  - 满足最低 `T1/T2/T3`，高风险域满足 `T4`
- `deploy_binding_ready`
  - plane-aware deployment binding 已配置并通过门禁
- `final_acceptance_ready`
  - 可进入统一集中验收
- `accepted`
  - 已由本节点统一验收通过

### 6. gate 聚合设计

统一 gate 分 4 层消费 `domain_onboarding`：

#### L0：`verify`

校验：

- `domain_onboarding_schema.yaml` 存在且合法
- `domains/<domain>.yaml` 结构完整
- 引用的 metadata 文件存在
- `acceptance_status` 只能按状态机推进

#### L1：`make gate`

校验：

- codegen 目标与元数据声明一致
- 所需 `object_types / actions / routes / views` 可被生成
- 不存在“声明了接入，但生成物缺失”

#### L2：`make gate`

校验：

- 最低测试层到位
- `T1/T2/T3` 是否满足领域最小接入包
- 高风险域是否声明并具备 `T4`

#### L3：`make gate-full`

聚合：

- 目标领域是否均达到 `final_acceptance_ready`
- 是否均具备 plane binding
- 是否均进入 portal projection
- 是否均可进入最终统一收口

### 7. codegen 责任边界

`domain_onboarding` 的 codegen 不直接生成业务代码，而生成“接入状态产物”。

建议边界：

- Web：
  - 领域接入状态面板
  - 接入缺项展示
  - 领域聚合 dashboard 卡片配置
- Go：
  - onboarding 汇总 DTO
  - gate/report 输入模型
- Python：
  - recommendation / analytics 域的接入状态消费模型
- App：
  - 非业务主链必需，可选生成只读状态 DTO 或 route metadata 引用常量

原则：

- codegen 负责接入状态与聚合展示
- 不直接替代各领域实际业务实现

### 8. plane-aware deployment binding 设计

当前 `deploy/shared/process_domain_mapping.yaml` 只表达 domain 归属，不足以支持三类面组合部署。

本次设计选型：

- **新增** `deploy/shared/process_domain_plane_mapping.yaml`
- 暂不直接替换旧文件
- 在 `/design` 与 `/dev` 期间保持双轨兼容

推荐结构：

```yaml
environments:
  integration:
    content-service:
      bindings:
        - domain: content
          planes: [user-plane]
          container_mode: dedicated
    seed-box:
      bindings:
        - domain: content
          planes: [platform-control-plane, product-control-plane]
          container_mode: sidecar
          co_locatable_with: [content-service]
          split_trigger: user_qps_growth
```

决策理由：

- 不破坏当前 domain-level mapping 与现有脚本
- 先引入 plane 级真相源，再逐步让 gate 与 deploy 迁移
- 更适合短期 `seed-box`、长期独立 Deployment 的双形态演进

### 9. 最终集中验收模型

最终集中验收由本节点统一执行，入口条件是：

- 所有目标领域 `acceptance_status >= final_acceptance_ready`
- 所有目标领域已进入 portal projection
- 所有目标领域 deploy binding 完整

统一验收聚合结果采用 3 态：

- `integration_pass`
  - 所有目标领域均已满足统一收口条件
- `integration_pass_with_gaps`
  - 主链通过，但存在不阻断发布的缺口
- `integration_blocked`
  - 存在领域未达到 `final_acceptance_ready`

### 10. 所有领域现状分析

当前仓库领域接入现状如下：

| 领域 | service.yaml | e2e.yaml | Go contract | Journey/Patrol | control-plane 可映射 | 设计结论 |
|---|---|---|---|---|---|---|
| `content` | 是 | 是 | 是 | 是 | 是 | `ready_for_parallel_dev` |
| `chat`（metadata: `messages`） | 是 | 是 | 是 | 是 | 是 | `ready_for_parallel_dev` |
| `circle`（metadata: `social`） | 是 | 是 | 是 | 是 | 是 | `ready_for_parallel_dev` |
| `user` | 是 | 是 | 是 | 是 | 是 | `ready_for_parallel_dev` |
| `assistant` | 是 | 否 | 否 | 部分 | 是 | `partial` |
| `rtc` | 是 | 否 | 是 | 否 | 部分 | `partial` |
| `integration` | 是 | 否 | 否 | 部分 | 部分 | `partial` |
| `recommendation` | 是 | 否 | 否 | 部分 | 是 | `partial` |
| `ops` | 是 | 否 | 否 | 否 | 是 | `partial` |
| `notification` | 是 | 否 | 否 | 否 | 部分 | `missing` |
| `realtime` | 是 | 否 | 否 | 否 | 部分 | `missing` |

说明：

- 第一批模板域：
  - `content / chat / circle / user`
- 第二批并行域：
  - `assistant / rtc / integration / recommendation / ops`
- 最缺资产域：
  - `notification / realtime`

### 11. 统一实施策略

本节点不在 `/design` 阶段同步完成所有领域落地实现；但后续 `/dev` 阶段采用**单会话统一实施**，而不是多会话并行。

推荐策略：

- 第 1 步：选择一个模板域
  - 推荐 `content`
  - 原因：三类面素材、`e2e.yaml`、Go contract、Patrol/journey 资产最完整
- 第 2 步：在同一会话中把模板域接入完整
  - 补 `domains/content.yaml`
  - 打通 verify / codegen / gate / plane binding / acceptance 回填
- 第 3 步：按同一模板复制到其余第一批领域
  - `chat / circle / user`
- 第 4 步：再推进第二梯队
  - `assistant / rtc / integration / recommendation / ops`
- 第 5 步：最后补齐最缺资产领域
  - `notification / realtime`
- 第 6 步：回到本节点做统一集中验收

该策略的核心不是“并行提速”，而是“模板先收敛，再复制降低漂移成本”。

因此：

- “所有领域服务做分析”在本阶段成立
- “所有领域服务在同一会话里统一推进接入”在后续 `/dev` 阶段也成立
- 但“所有领域在当前 `/design` 阶段同步实施落地”不成立，否则会破坏 SDD 分层

## 适用场景与约束

- **适用**：多领域需要在同一实施会话中统一接入统一控制面，并最终集中验收的场景
- **约束**：实现顺序必须仍然是 metadata → verify → codegen → minimal glue → tests → acceptance
- **局限性**：当前设计仍未实现 schema 文件、verify 脚本与部署脚本，需要进入 `/dev` 才能真正打通

## 未来演进

- 在 `/dev` 阶段先以 `content` 作为模板域验证设计有效性
- 在同一会话中把模板复制到 `chat / circle / user`
- 再继续向 `assistant / recommendation / rtc / realtime / notification / integration / ops` 推广
- 后续把 `ops-portal` 直接升级为统一接入状态中心，消费 gate 聚合与最终验收状态
