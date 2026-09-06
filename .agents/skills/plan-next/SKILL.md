---
name: plan-next
description: Close out a development round by reconciling the plan against real artifacts and adjudicating every gap as fix-now / OPEN / out-of-scope, then generate the next round's plan. Use when the user says 下一轮做什么, 计划复核, 闭环自检, or 这轮做完了吗.
metadata:
  kind: workflow
  command: /plan-next
---

# plan-next

## 触发与输入

用于根据真实产物和证据收口当前轮次，并产生最小下一轮。输入是用户目标、当前 plan/todo、diff、测试/gate/Review 与 OPEN；调用前不要求 owner manifest。角色交互只引用 `quwoquan_ops/policies/human_agent_delivery_contract.yaml#workflow_interaction_binding.bindings.plan-next`，可见输出由 canonical projector 生成。

## 执行

1. PRE 从用户目标、plan/diff 与已知路径确定本轮 exact target；读取最近子树 `AGENTS.md`，best-effort 运行默认 compact `make feature-context TARGET=<exact-path>`。唯一 owner 解析成功时保存 stdout 的 immutable exact ref；无 owner、多 owner或解析失败时记录 typed 结果，并基于当前 Git 快照继续只读收口，不因此 `GATE_BLOCK` 整个 plan-next。
2. 逐项比对计划与当前文件、契约、生成物、测试、runtime/release/UAT 证据，不信任完成标记。
3. 每个 gap 只能裁决为 fix-now、最低可关闭节点 `OPEN-###` 或 Out of Scope；code-health `PR_WARN` 同样只允许这三种去向。scope 内 required blocker 未闭合时不生成虚假下一轮。
4. 已收口时按依赖与用户价值生成可验收的下一轮；默认不自动派 Reviewer。

## 完成证据

交付 immutable ref（若可用）及 typed owner 解析结果、本轮真实完成项、分层验证、每个 gap 的唯一去向、剩余 blocker 和下一轮可测目标；fingerprint 不匹配时明确标记 stale。

## 失败与停止

计划身份或 target 无法收窄、证据过期、gap 无去向或 required blocker 被包装为完成时 `GATE_BLOCK`；owner 不明本身不阻断只读 plan-next，但不得猜测任何 mutation owner，也不用更换计划绕过失败。

## 条件性交接

下一轮交给最早足以闭环的 explore/prd/design/dev 等 Skill，并传递 exact target 与 ref（若可用）；进入 prd/design/dev 等 mutation Skill 前仍须取得唯一 owner/ref。只有 canonical 六类 handoff 触发成立时持久交接。
