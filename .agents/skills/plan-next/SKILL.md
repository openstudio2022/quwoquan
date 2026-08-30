---
name: plan-next
description: Close out a development round by reconciling the plan against real artifacts and adjudicating every gap as fix-now / OPEN / out-of-scope, then generate the next round's plan. Use when the user says 下一轮做什么, 计划复核, 闭环自检, or 这轮做完了吗.
metadata:
  kind: workflow
  command: /plan-next
---

# plan-next

## 触发与输入

用于根据真实产物和证据收口当前轮次，并产生最小下一轮。输入是当前 plan/todo、owner manifest、Git diff、测试/gate/Review 结果和 OPEN。

自然语言触发与显式 Skill 调用同轨，字段、闭集与审计隔离只引用 `quwoquan_ops/policies/human_agent_delivery_contract.yaml#workflow_interaction_binding.plan-next`：

- PRE：`progress_update` / `feedback_knowledge_distillation` / `engineering_delivery_owner`。

## 执行

1. 逐项比对原计划与当前文件、契约、生成物、测试、runtime/release/UAT 证据，不信任完成标记。
2. 每个 gap 只能裁决为 fix-now、最低可关闭节点 `OPEN-###` 或 Out of Scope；禁止悬空/中央 backlog。
3. 若当前轮仍有 scope 内 required blocker，保持当前轮不生成虚假下一轮。已收口时按依赖与用户价值生成可验收的下一轮。
4. 默认不自动派 Reviewer；用户显式要求 Review 时也受 Review Skill 的证据与角色预算限制。

- 执行中：`decision_request` / `delivery_planning_authorization` / `$route`。

`$route` 表示按当前决定责任动态路由；Skill 不复制 envelope schema，所有可见输出统一由 canonical projector 生成。

## 完成证据

交付本轮真实完成项、分层验证、每个 gap 的唯一去向、剩余 blocker 和下一轮可测目标。当前指纹不匹配时标记证据过期。

- POST：`completion_report` / `delivery_planning_authorization` / `engineering_delivery_owner`。

## 失败与停止

计划身份不明、owner 冲突、证据过期、gap 无去向或 required blocker 被包装为完成时 `GATE_BLOCK`。不用更换计划来绕过当前失败。

## 条件性交接

六类触发（跨会话未完成、多人并行、环境/发布、外部阻断、证据复用、用户显式要求）统一调用 canonical handoff producer；普通闭环不落持久交接。
