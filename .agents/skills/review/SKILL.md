---
name: review
description: Build a bounded evidence-first Review plan from the shared owner manifest, dispatch one workflow primary and at most one profile specialist at POST, and consolidate typed GATE_BLOCK / PR_WARN / advisory results. Use whenever the user asks for 评审, 审核, 检视, plan review, code review, 验证, or 准出检查.
metadata:
  kind: workflow
  command: /review
---

# review

## 触发与输入

用户显式要求评审/验证/准出，或增量进入准出（lane→`dev1.0` PR、handoff、release）时使用；开发 workflow 的 POST 默认不派审，不自动进入本 Skill。输入是 workflow、segment、deliverable、scope、changed paths 与 evidence；直接 Review 的 PRE 调用前不要求 owner manifest。角色交互只引用 `quwoquan_ops/policies/human_agent_delivery_contract.yaml#workflow_interaction_binding.bindings.review`，可见输出由 canonical projector 生成。

## 执行

1. PRE 从用户目标、plan/diff 与已知路径确定 exact target；读取最近子树 `AGENTS.md`。直接 Review 运行默认 compact `make feature-context TARGET=<exact-path>` 并保存 stdout immutable exact ref；所属开发 workflow 的 POST 必须原样消费其 PRE 已保存的同一 ref。
2. 生成 Review plan 时传 `--context-manifest <immutable-ref>`；PRE 不派 Reviewer。profile 只由 registry 根据 changed paths + deliverable 派生，不从 owner manifest 读取。
3. POST 先按 plan.evidence ID 去重执行一次命名 evidence；required 失败立即停止。随后只派 workflow primary 与最高优先级的一名 specialist，Reviewer 不补跑 gate。
4. 汇总 typed finding；修复后仅允许 initial plan 的 finding owner 定向复审，不自动重试或形成 rereview chain。

## 完成证据

交付 exact target/ref、plan、每条 evidence 实际结果、角色完成状态、去重 finding 与 typed terminal；只有 required evidence/Reviewer 完成、fingerprint 匹配且无 GATE_BLOCK 才可准出。

## 失败与停止

immutable ref 缺失、摘要/target/scope/owner/fingerprint stale，evidence 失败、Reviewer incomplete/cancelled 或预算超限时按 canonical terminal 停止；不复用 stale evidence。

## 条件性交接

finding 回交其 owner workflow；只有 canonical 六类 handoff 触发成立时持久交接。Reviewer PASS 仅是评审证据，不签发 Human 或发布 authority。
