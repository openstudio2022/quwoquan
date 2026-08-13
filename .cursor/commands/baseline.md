---
name: /baseline
id: baseline
category: Specification
description: 在需求和设计收敛时冻结可直接开发的当前基线
---

# /baseline

目标：在需求和设计收敛时冻结可直接开发的当前基线。

准入：父链唯一；REQ 与 UAT/DOM/SIT/GWT 可观察且均可被三层测试绑定；metadata owner 明确；三层测试可实现；无重大设计分叉；与并行会话无未裁决的同文件冲突（`git status` 交集已确认互不覆盖）。

执行：对齐父链 `spec.md`、必要 `design.md`、metadata 引用和节点 OPEN；运行 `make verify-feature-tree`、`make feature-context TARGET=<target>` 与 `make feature-tree-change-report`。

产出不包含 acceptance YAML、registry/index、changelog、任务文件或完成状态。实施任务只存在当前会话计划；长期未完成事项写节点 OPEN。

方案未收敛、OPEN `block` 未处置、测试无法映射验收锚点或并行冲突未裁决时返回 `GATE_BLOCK`，退回 `/prd` 或 `/design`。

自然语言等价触发："冻结基线""需求稳定了""把规格设计收齐"。
