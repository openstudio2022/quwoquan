---
name: prd
description: Update the currently-valid spec.md and testable acceptance anchors for a change, without implementing anything. Every acceptance must be bindable by a real test. Use when the user says 写 PRD, 冻结需求, 明确规格, 明确范围, 明确验收, or when a change needs its spec updated before code.
metadata:
  kind: workflow
  command: /prd
---

# prd

## 触发与输入

用于新增/修改 Feature spec、冻结范围与可测验收，不实现代码。输入必须包含 owner manifest、用户价值、In/Out Scope、当前 OPEN 与验收层。

## 执行

1. 在最低可关闭节点更新 AppRoot Journey/UAT、L1 DOM、L2 SIT 或 L3 REQ/GWT；不跨层复制事实。
2. 每条验收写成 GIVEN/WHEN/THEN/AND 可观察结果，声明 `local_contract/api_integration/user_acceptance` 证据层和可绑定的 `spec_ref`。
3. 字段、枚举、operation、错误码只引用 canonical contracts。未实现事实进 `OPEN-###`，不写中央 backlog。
4. 运行 `make verify-feature-tree`。PRE 由主会话自检输入，不派 Reviewer；POST 按 `review` Skill 执行命名 evidence 后至多派 Product 主审与一名专审。

## 完成证据

当前有效 spec 包含唯一父链、范围、REQ/验收锨点、证据层和 OPEN 去向；`verify-feature-tree` 与 POST Review 结果按当前指纹报告。

## 失败与停止

用户价值、范围、owner、可测结果或 contract owner 不唯一时 `GATE_BLOCK`，回 `explore`。门禁或 required Review 失败时保留 typed blocker，不进 design/dev。

## 条件性交接

普通闭环只交付 spec、验证和未决项。只有跨会话、多人并行、外部阻断或下游需复用证据时，才持久化 owner/范围/验收/指纹，并交给 design 或 dev。
