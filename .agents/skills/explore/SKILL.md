---
name: explore
description: Read-only workflow that locates where a change belongs before any code or spec is written - AppRoot Journey, L1/L2/L3 parent chain, scope, acceptance intent, parallel-session conflicts. Use at the start of any non-trivial change, and when the user says 先分析, 看归属, 怎么拆, 有哪些风险, or where does this go.
metadata:
  kind: workflow
  command: /explore
---

# explore

## 触发与输入

用于非平凡变更的只读定位。输入是用户目标、已知路径、候选 diff 与共享 writer 状态；调用前不要求 owner manifest。角色交互只引用 `quwoquan_ops/policies/human_agent_delivery_contract.yaml#workflow_interaction_binding.bindings.explore`，可见输出由 canonical projector 生成。

## 执行

1. PRE 先从用户目标、当前 plan/diff 与已知路径确定一个 exact target；目标仍有歧义时只读收窄，不猜 owner。
2. 已知目标路径时读取最近子树 `AGENTS.md`，再 best-effort 运行默认 compact `make feature-context TARGET=<exact-path>`；唯一 owner 解析成功时保存并按 stdout 返回的 immutable exact ref 消费 owner chain、canonical contexts、OPEN 与 applicable agents；无 owner、多 owner或解析失败时记录 typed owner 解析结果，并基于当前 Git 快照继续只读定位。
3. 检查 HEAD/status、目标 diff 与 writer，明确 In/Out Scope、验收意图、依赖、共享写点和最早足以闭环的后继 Workflow Skill。全程不修改文件、不派 Reviewer。

## 完成证据

交付 exact target、immutable owner manifest ref（若可用）、typed owner 解析结果、父链（若可解析）、范围、验收层、风险与建议下游；ref unavailable 时必须明确记录，证据来自当前 Git 快照和可用的 exact ref，不来自固定路径或对话印象。

## 失败与停止

无 owner、多 owner或 owner 解析失败不阻断只读 explore；记录 typed 结果，并报告并行冲突风险与共享写点。只有 target、验收意图或其他只读定位前提经收窄后仍无法确定时才停止；绝不能据此进入 mutation，也不得向 prd/design/dev 猜测 mutation owner。

## 条件性交接

确认需要写规格、设计或实现后，分别交接 prd、design 或 dev，并传递 exact target 与 immutable ref（若可用）；下游进入 mutation 前仍须取得唯一 owner/ref。只有跨会话未完成、多人并行、环境/发布、外部阻断、证据复用或用户显式要求时才生成 canonical handoff。
