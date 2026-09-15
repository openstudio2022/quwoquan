---
name: plan-next
description: Close out a development round by reconciling the plan against real artifacts and adjudicating every gap as fix-now / OPEN / out-of-scope, then generate the next round's plan. Use when the user says 下一轮做什么, 计划复核, 闭环自检, or 这轮做完了吗.
metadata:
  kind: workflow
  command: /plan-next
---

# plan-next

## 触发与输入

用于根据真实产物和证据收口当前轮次，并产生最小下一轮。输入是用户目标、当前 plan/todo、diff、测试/gate/Review 与 OPEN。

## 执行

1. PRE 从用户目标、plan/diff 与已知路径确定本轮 exact target；读取最近子树 `AGENTS.md`，best-effort 运行 `make feature-context TARGET=<exact-path>`：唯一 owner 时保存 immutable ref，否则记录 typed 结果并基于当前 Git 快照继续只读收口，不因此 `GATE_BLOCK`。
2. 逐项比对计划与当前文件、契约、生成物、测试、runtime/release/UAT 证据，不信任完成标记；lane 落后本地 `dev1.0` 超过 `worktree_policy.yaml#resync_reminder_behind_commits` 时把 `sync-lane-from-dev` 列入下一轮首项。
3. 每个 gap 只能裁决为 fix-now、最低可关闭节点 `OPEN-###` 或 Out of Scope；code-health `PR_WARN` 按 canonical `candidate_review_closure` 对原始 finding identity 逐项裁决，复用当前 artifact 与 candidate fingerprint；fix-now 需新验证消除原有效 warning，OPEN 必须当前最低 owner 有效，out-of-scope 需客观边界证据。声明 replacement 时对账旧入口、消费者与实现/配置/测试退役或保留依据及扫描/测试 evidence；无替换不造删除清单，unknown 动态入口不自动删除。scope 内 required blocker 未闭合时不生成虚假下一轮，不以 OPEN 抵消高风险 blocker。
4. 若本轮触及手写源码，运行 `make code-health-hotspots OWNER=<owner-scope>`：只有连续两期在榜（`ACTIONABLE`）且可行动的热点才裁决为最低 owner `OPEN-###` 或 Out of Scope，单期热点只记录不开 OPEN；输出 `unavailable` 时按无热点事实继续，不阻断。
5. 已收口时按依赖与用户价值生成可验收的下一轮；默认不自动派 Reviewer。

## 完成证据

交付 immutable ref（若可用）及 typed owner 解析结果、本轮真实完成项、分层验证、每个 gap 的唯一去向、剩余 blocker 和下一轮可测目标；fingerprint 不匹配时明确标记 stale。

## 失败与停止

计划身份或 target 无法收窄、证据过期、gap 无去向或 required blocker 被包装为完成时 `GATE_BLOCK`；owner 不明本身不阻断只读 plan-next，但不得猜测任何 mutation owner，也不用更换计划绕过失败。

## 条件性交接

下一轮交给最早足以闭环的 explore/prd/design/dev 等 Skill，并传递 exact target 与 ref（若可用）；进入 mutation Skill 前仍须取得唯一 owner/ref。持久交接语义见 continue Skill。
