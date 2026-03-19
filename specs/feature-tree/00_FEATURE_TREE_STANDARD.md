# 特性树文档标准（Journey / Scenario 版）

> **权威**：特性树节点的治理信息只通过以下四类节点文档表达：
>
> - `spec.md`
> - `design.md`
> - `plan.yaml`
> - `acceptance.yaml`
>
> 另有一条独立的增量变更流：
>
> - `specs/changelog/CR-*.yaml`
>
> 本标准与三层层级定义绑定，只适用于：
>
> - `L1_capability`
> - `L2_journey`
> - `L3_scenario`
>
> 会话级 todo 只存在于 AI 会话中，不占目录层，也不属于正式治理文档。

---

## 一、适用范围

本标准适用于全仓端云一体化开发，包括：

- `quwoquan_app`
- `quwoquan_service`
- `contracts/metadata`
- `specs/feature-tree`
- `specs/changelog`

任何子域规范只能补充细节，不能替代本标准。

---

## 二、节点文档与增量文档

### 2.1 `L1_capability`

每个 `L1_capability` 目录必须具备以下四类节点文档：

- `spec.md`
- `design.md`
- `plan.yaml`
- `acceptance.yaml`

职责：

- 说明能力边界
- 说明关键旅程、NFR、发布治理
- 组织其下的 `L2_journey`

### 2.2 `L2_journey`

每个 `L2_journey` 目录必须具备以下四类节点文档：

- `spec.md`
- `design.md`
- `plan.yaml`
- `acceptance.yaml`

职责：

- 作为端到端用户旅程容器
- 承载 Journey 范围、边界、跨 Scenario 组合规则与 Journey 级验收

### 2.3 `L3_scenario`

每个 `L3_scenario` 目录必须具备以下四类节点文档：

- `spec.md`
- `design.md`
- `plan.yaml`
- `acceptance.yaml`

职责：

- 作为最小独立实施与验证单元
- 承载单环节场景、异常边界、实施计划、验收和测试证据

### 2.4 `plan.yaml`

`plan.yaml` 是节点级正式实施计划，不是目录层，也不是会话 todo。

它只回答：

- 稳定切片是什么
- 切片依赖顺序是什么
- 每个切片引用哪些 `acceptance_ref`
- 每个切片的退出条件与预期证据是什么

禁止行为：

- 把 `plan.yaml` 写成对话记录
- 把会话 todo 回写成正式 plan
- 让 `plan.yaml` 维护第二套需求规格

### 2.5 `specs/changelog/CR-*.yaml`

`CR` 文件不放在节点目录下，统一放在 `specs/changelog/`。

职责：

- 记录一次增量变更包的 delta
- 记录受影响的 `L2_journey / L3_scenario`
- 记录是否需要 replan / redesign / retest
- 记录本轮增量的版本修订 `revision`

禁止行为：

- 用 `specs/changelog/` 复刻一套特性树层级
- 在 CR 中维护第二套归属关系
- 让 CR 替代 `spec.md`、`design.md`、`acceptance.yaml`、`plan.yaml`

---

## 三、节点文档职责

| 文档 | 作用 |
|------|------|
| `spec.md` | 说明为什么做、做什么、不做什么、适用边界 |
| `design.md` | 说明怎么做、为什么这样做、方案对比、关键决策 |
| `plan.yaml` | 说明稳定切片、依赖顺序、`acceptance_ref`、退出条件 |
| `acceptance.yaml` | 说明 Journey / Scenario 验收标准、测试层映射、证据、执行门禁 |
| `specs/changelog/CR-*.yaml` | 说明一次增量变更包的 delta 与影响范围 |

### 3.1 禁止第五类节点治理文档

禁止在特性树节点下新增以下独立治理文档：

- `tasks.md`
- `README.md`
- `analysis-*.md`
- `architecture.md`
- `diagram.md`
- `*-规划.md`
- `*-设计说明.md`

分析、规划、架构说明、图示说明都必须汇入四类节点文档内部；增量变更必须汇入 `specs/changelog/CR-*.yaml`。

---

## 四、文档内容要求

### 4.1 `spec.md`

必须包含：

- 节点层级与定位
- 背景与动机
- 目标用户或平台价值
- 功能范围
- Out of Scope
- 约束与适用边界
- 对标输入与吸收结论
- 验收重点

### 4.2 `design.md`

必须包含：

- 设计动因
- 上游输入评审
- 对标输入分析
- 至少两套方案对比
- 选型决策
- 关键设计决策
- TDD / ATDD 策略
- 未来演进

若是 `L1_capability`，还必须在 `design.md` 内包含架构图示或等价文本说明，不得外置第五类节点文档。

### 4.3 `plan.yaml`

必须包含：

- `version`
- `node`
- `derived_from`
- `slices`

每个 slice 至少包含：

- `id`
- `title`
- `acceptance_refs`
- `depends_on`
- `planned_evidence`
- `done_when`
- `status`

### 4.4 `acceptance.yaml`

必须包含：

- `version`
- `feature`
- `level`
- `execution`
- `scope`
- `journey_acceptance` 或 `scenario_acceptance`

`L2_journey` 的核心验收项至少包含：

- `title`
- `journey`
- `scenario_refs`
- `done_when`
- `release_guardrails`
- `evidence`
- `tests`
- `status`

`L3_scenario` 的核心验收项至少包含：

- `title`
- `scenario`
- `journey_step`
- `done_when`
- `edge_cases`
- `linked_plan_items`
- `evidence`
- `tests`
- `status`

测试层只允许使用：

- `T1`
- `T2`
- `T3`
- `T4`

### 4.5 `specs/changelog/CR-*.yaml`

必须包含：

- `id`
- `title`
- `slug`
- `revision`
- `status`
- `affected_nodes`
- `entries`

每条 entry 至少包含：

- `timestamp`
- `summary`
- `reason`
- `changed_documents`
- `impact`

---

## 五、目录与索引规则

- 特性树目录只允许三层目录深度：`L1_capability / L2_journey / L3_scenario`
- `tree_index.yaml` 是结构索引唯一真相源
- `specs/changelog/` 是增量变更的唯一真相源
- 不再允许脚手架、命令文案、辅助树文件维护第二套不一致层级定义

违规即失败：

- 发现三层以上目录
- 发现 `L4` 或 `L5`
- 发现节点目录仍以 `tasks.md` 作为正式计划文档
- 发现 `acceptance.yaml` 使用旧 `level`
- 发现旧层级残留在脚手架或 gate 中

---

## 六、节点生命周期

每个正式节点在 `tree_index.yaml` 中通过 `status` 表示生命周期：

- `specified`
- `in_progress`
- `completed`
- `cancelled`
- `deprecated`

### 6.1 `L1_capability`

可长期存在，通常不会频繁归档变动。

### 6.2 `L2_journey`

是关键用户旅程与发布收口容器。

### 6.3 `L3_scenario`

是实施、验证、提交的核心对象。

### 6.4 `plan slice`

不进入 `tree_index.yaml`，通过 `plan.yaml` 管理状态。

### 6.5 `session todo`

只存在于会话上下文中，不写回特性树。

---

## 七、与命令和流程的衔接

- `/explore`
  - 确认 `L1_capability`、`L2_journey` 与目标 `L3_scenario`
- `/prd`
  - 创建或更新 Journey / Scenario 的 `spec.md + acceptance.yaml`
  - 创建或更新对应 `CR`
- `/design`
  - 完成 Journey / Scenario 的 `design.md + plan.yaml`
- `/dev`
  - 消费 `plan.yaml` 中的 slices，派生本次会话 todo
- `/verify`
  - 复核 `L3_scenario` 完成度、`L2_journey` 受影响验收与测试证据
- `/commit`
  - 提交已完成的 slice 与对应 CR 范围

---

## 八、总结

Journey / Scenario 治理模型下，特性树节点的唯一正式结构为：

```text
L1_capability
  └── L2_journey
        └── L3_scenario
              ├── spec.md
              ├── design.md
              ├── plan.yaml
              └── acceptance.yaml

specs/changelog/
  └── CR-YYYYMMDD-NNN-slug.yaml
```

四类节点文档服务于 `L1_capability`、`L2_journey` 与 `L3_scenario`。  
会话级 todo 是执行层，不再是文档层；增量变更通过 `CR` 独立记录。
