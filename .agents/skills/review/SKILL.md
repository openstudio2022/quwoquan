---
name: review
description: Build a bounded evidence-first Review plan from PRE owner identity plus POST candidate evidence, dispatch one primary and at most one specialist, and consolidate typed GATE_BLOCK / PR_WARN / advisory results. Use whenever the user asks for 评审, 审核, 检视, plan review, code review, 验证, or 准出检查.
metadata:
  kind: workflow
  command: /review
---

# review


> Named evidence receipt 的 `evidence_class` / `admission_eligible` 是准出事实：dirty mutable workspace 结果仅为 `feedback_only`，可供普通显式 Review 开发反馈，但不得复用为 handoff、scope/release readiness 或 governance admission 证据。

## 触发与输入

用户显式要求评审/验证/准出，或增量进入准出（lane→`dev1.0` PR、handoff、release）时使用；开发 workflow 的 POST 默认不派审，不自动进入本 Skill。输入是 workflow、segment、deliverable、scope、changed paths 与 evidence。

## 执行

1. PRE 从用户目标、plan/diff 与已知路径确定 exact target；读取最近子树 `AGENTS.md`。直接 Review 运行 `make feature-context TARGET=<exact-path>` 并保存 immutable ref；所属开发 workflow 的 POST 必须消费 PRE 已保存的 owner identity ref，并基于 exact changed paths 生成 current candidate evidence ref。
2. 生成 Review plan 时传 `--owner-identity <immutable-ref> --candidate-evidence <candidate-ref>`；PRE 不派 Reviewer。profile 只由 registry 根据 changed paths + deliverable 派生，不从 owner manifest 读取。
3. POST 先按 plan.evidence ID 去重执行一次命名 evidence；required 失败立即停止。随后只派 workflow primary 与最高优先级的一名 specialist，Reviewer 不补跑 gate。
4. 汇总 typed finding；修复后仅允许 initial plan 的 finding owner 定向复审，不自动重试或形成 rereview chain。

## 完成证据

交付 exact target/ref、plan、每条 evidence 实际结果、角色完成状态、去重 finding 与 typed terminal；只有 required evidence/Reviewer 完成、fingerprint 匹配且无 GATE_BLOCK 才可准出。

## 失败与停止

immutable ref 缺失、摘要/target/scope/owner/fingerprint stale，evidence 失败、Reviewer incomplete/cancelled 或预算超限时按 canonical terminal 停止；不复用 stale evidence。

## 条件性交接

finding 回交其 owner workflow；持久交接语义见 `continue` Skill，触发成立时交接必须携带 exact owner/candidate、named evidence、Reviewer result 与 consolidation。Reviewer PASS 与当前 Human 聊天同意都只是输入证据，不签发 Human、发布或 Prod authority；正式 provider 未接入时保持 blocked/OPEN。
