# 增量变更台账（CR changelog）

本目录承载 Journey / Scenario 治理模型下的增量变更流。

## 目标

- 记录一次增量变更包的 delta
- 记录受影响的 `L2_journey / L3_scenario`
- 记录本轮变更是否需要 `replan / redesign / retest`
- 记录同一变更请求的连续修订 `revision`

## 命名规则

文件命名必须为：

```text
CR-YYYYMMDD-NNN-<semantic-slug>.yaml
```

示例：

```text
CR-20260318-001-owner-subaccount-homepage-unification.yaml
CR-20260318-002-profile-chat-entry-alignment.yaml
```

约束：

- `CR-YYYYMMDD-NNN` 保证唯一
- `<semantic-slug>` 保证可读
- 文件名保持稳定，修订通过文件内的 `revision` 递增

## 结构约束

- 一个 CR 可以影响多个 `L2_journey / L3_scenario`
- `affected_nodes` 必须显式列出受影响节点路径
- CR 只能记录 delta，不能复制一份完整 `spec.md / design.md / acceptance.yaml / plan.yaml`
- 本目录不能按 `L1/L2/L3` 重建第二套特性树

## 与节点文档的关系

- `spec.md`：当前规格真相源
- `design.md`：当前设计真相源
- `acceptance.yaml`：当前验收真相源
- `plan.yaml`：当前稳定实施计划真相源
- `CR-*.yaml`：变更过程与影响真相源

## 最小字段

每个 CR 文件至少应包含：

- `id`
- `title`
- `slug`
- `revision`
- `status`
- `affected_nodes`
- `entries`

每条 entry 至少应包含：

- `timestamp`
- `summary`
- `reason`
- `changed_documents`
- `impact`

模板见：

- `specs/changelog/templates/CR-template.yaml`
