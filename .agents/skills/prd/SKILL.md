---
name: prd
description: Update the currently-valid spec.md and testable acceptance anchors for a change, without implementing anything. Every acceptance must be bindable by a real test. Use when the user says 写 PRD, 冻结需求, 明确规格, 明确范围, 明确验收, or when a change needs its spec updated before code.
metadata:
  kind: workflow
  command: /prd
---

# prd

更新当前有效规格与验收锚点。**不做实现。** 五段执行契约见根 `AGENTS.md`。

## 触发

- 显式命令 `/prd`。
- 自然语言：写 PRD、冻结需求、明确规格、明确范围、明确验收，或改动需要先更新 spec。

## 输入

- `explore` 的 HANDOFF：目标父链、用户价值、范围、关键依赖（缺任一项回 `explore`）。
- 现有 Journey / Scenario / REQ 与父链 `OPEN`。

## 角色

主会话扮演 **spec-owner**：只拥有规格与验收，不同时扮演评审者；评价交给内置评审的只读角色。

## 执行

自由度：中（层级模板固定，表述自由）。

范围或验收未冻结时，先按
[explore/references/decision-tree-interview.md](../explore/references/decision-tree-interview.md)
把决策问穿再落笔。随后按 [`specs/feature-tree/README.md`](../../../specs/feature-tree/README.md)
更新对应 `spec.md`。各层各写各的，不越层：

| 层 | 写什么 |
|---|---|
| AppRoot | Journey / Scenario / UAT |
| L1 | 领域边界 / REQ / DOM / 工程归属 |
| L2 | 能力范围 / REQ / SIT |
| L3 | 独立价值 / REQ / GWT |

- 跨域 Journey 只在 AppRoot 写完整叙事，参与节点写自身职责与反向链接。
- 字段、path、operation、surface、route、error、event、metric 只引用 metadata ID。
- 验收只保留改变产品契约的代表场景；排列组合、路径、命令与结果留在测试代码与运行输出。
- [MUST] 每条 GWT/SIT 满足：**GIVEN 可注入、WHEN 可触发、THEN 可断言**，且经导出面或对象级
  typed port 观察。写不出观察方式的验收**当场改写**，不留给实现阶段发明旁路。
- [MUST] 未完成能力、阻断、风险写到**最低可关闭节点**的 `OPEN-###`；完成判定必须引用验收锚点。
  完成项直接成为当前 REQ，不保留完成状态。
- [MUST NOT] 创建 acceptance YAML、registry、index、changelog、任务台账或成熟度矩阵。

## 交付件

**spec 增量**：规格 diff、验收锚点、OPEN 变化，以及「是否达到 design 门槛」的明确判定。

送审前自检：

- 无占位符、无自相矛盾；
- 每条验收都能点名将绑定它的测试层；
- 权限、生命周期、异常恢复、SLO、灰度回滚、canonical metadata 均已明确或已挂 OPEN。

## 内置评审

- PRE：调 `review`（workflow=`prd`，segment=PRE）确认 `explore` HANDOFF 输入齐全。
- POST：调 `review`（workflow=`prd`，segment=POST，deliverable=`spec-node`），
  典型角色 product + user + ux + test（验收可测性），gate 为 `make verify-feature-tree`；
  同时跑 `make feature-tree-change-report` 确认影响面与预期一致。

## 失败与停止

- 不写 DEC、不实现。
- 验收无法被真实测试绑定、或必答质量维度未明确且未挂 OPEN：`GATE_BLOCK`。

## HANDOFF

- **产出物**：目标父链的 `spec.md` 增量；确有设计变化时附上层设计输入。
- **未决项去向**：新增或变更的 `OPEN-###` 及其所在节点。
- **唯一合法下游**：达到设计门槛（对象边界、跨域/跨服务、外部依赖、状态迁移、质量权衡、
  观测或回滚分叉）交给 `design`；否则直接交给 `dev`。交接前确认基线可冻结——父链唯一、
  REQ 与 UAT/DOM/SIT/GWT 均可被三层测试绑定、metadata owner 明确、与并行会话无未裁决冲突。
- **证据链**：`make verify-feature-tree` 与 `make feature-tree-change-report` 输出。
