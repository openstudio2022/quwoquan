# 迁移样板：`profile-homepage-redesign`

本样板用于说明如何把一个现有的 `L2_feature / L3_story / tasks.md` 组合迁移到新的 `L2_journey / L3_scenario / plan.yaml` 模型，而不直接改写业务内容。

## 当前节点

现有路径：

- `specs/feature-tree/user-identity-profile-relationship/profile-homepage-redesign/`
- `specs/feature-tree/user-identity-profile-relationship/profile-homepage-redesign/owner-subaccount-homepage-unification/`
- `specs/feature-tree/user-identity-profile-relationship/profile-homepage-redesign/plan.yaml`
- `specs/feature-tree/user-identity-profile-relationship/profile-homepage-redesign/owner-subaccount-homepage-unification/plan.yaml`
- `specs/changelog/CR-20260318-001-profile-homepage-redesign-journey-scenario-migration.yaml`

当前问题：

- `L2` 同时承载了旅程目标、文件迁移、UI 实现细节与测试 case 数量。
- `L3` 同时承载了主体模型、元数据基线、统一 UI、滚动动效、观测与回滚。
- `tasks.md` 混入了设计补丁、schema 草案和任务执行三种职责。

## 迁移目标

```text
L2_journey: profile-homepage-redesign
  ├── L3_scenario: owner-subaccount-homepage-unification
  ├── L3_scenario: profile-shell-ui-unification
  └── L3_scenario: profile-motion-and-sticky-coordination
```

## 文档拆分建议

### `L2_journey`

保留：

- 统一主页的端到端用户旅程
- 跨场景 IA 与 route / metadata 单一真相源要求
- 发布 guardrails、feature flag、回滚与观测收口

移出：

- 具体文件迁移任务
- 组件实现细节
- 具体 widget / journey case 数量

### `L3_scenario: owner-subaccount-homepage-unification`

保留：

- 主体模型、资料同步、关系能力与互动活动的单场景目标
- 该场景负责的异常边界
- 对应 `plan.yaml` slices 与 `T1/T2/T3` 证据

移出：

- 与统一 ProfileShell 视觉壳层无关的 UI 细节
- 与滚动/吸顶动效强绑定的实现方案

### 新增 `L3_scenario`

- `profile-shell-ui-unification`
  - 负责统一壳层、Header、ActionBar、一级/二级 Tab 结构
- `profile-motion-and-sticky-coordination`
  - 负责单主滚动坐标系、拉伸、回弹、identity pin、primary tab pin

## `plan.yaml` 切片示意

`owner-subaccount-homepage-unification/plan.yaml`

- `P1`：冻结主体模型与 metadata
- `P2`：收口资料同步写入与关系能力
- `P3`：补齐互动活动读契约与证据

`profile-shell-ui-unification/plan.yaml`

- `P1`：统一 ProfileShell 入口与壳层骨架
- `P2`：统一一级/二级 Tab 与动作区

`profile-motion-and-sticky-coordination/plan.yaml`

- `P1`：单主滚动坐标系
- `P2`：下拉拉伸与回弹
- `P3`：identity pin / primary tab pin

`profile-homepage-redesign/plan.yaml`

- `P1`：重定 Journey 边界
- `P2`：冻结 Scenario 拆分拓扑
- `P3`：迁移 Journey acceptance schema
- `P4`：回填新增 Scenario 节点
- `P5`：退出 current `tasks.md` 主导

## CR 建议

建议创建：

```text
specs/changelog/CR-20260318-001-profile-homepage-redesign-journey-scenario-migration.yaml
```

`affected_nodes` 至少包括：

- `specs/feature-tree/user-identity-profile-relationship/profile-homepage-redesign`
- `specs/feature-tree/user-identity-profile-relationship/profile-homepage-redesign/owner-subaccount-homepage-unification`

若拆出新 Scenario，再把新增 Scenario 路径补入。

## pilot 执行顺序

1. 先执行 Journey 级 `P1/P2`，冻结 L2 的旅程边界和 Scenario 拆分。
2. 再执行现有 Scenario 的 `P1/P2/P3`，把主体模型、同步和互动契约从 UI/动效中剥离出来。
3. 接着改写 L2 与现有 Scenario 的 acceptance schema。
4. 最后创建两个新 Scenario 节点，并把统一壳层与滚动动效迁移过去。
