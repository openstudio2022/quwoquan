---
name: explore
description: Read-only workflow that locates where a change belongs before any code or spec is written - AppRoot Journey, L1/L2/L3 parent chain, scope, acceptance intent, parallel-session conflicts. Use at the start of any non-trivial change, and when the user says 先分析, 看归属, 怎么拆, 有哪些风险, or where does this go.
metadata:
  kind: workflow
  command: /explore
---

# explore

## 触发与输入

用于非平凡变更的读取定位，或用户要求归属、拆分、风险分析时触发。输入是用户目标、候选 spec/代码路径和当前 Git/活跃 writer 状态。

自然语言触发与显式 Skill 调用同轨，字段、闭集与审计隔离只引用 `quwoquan_ops/policies/human_agent_delivery_contract.yaml#workflow_interaction_binding.explore`：

- PRE：`progress_update` / `concept_intake` / `business_sponsor`。

## 执行

1. 只读检查 HEAD、status、目标 diff 与 writer，不修改文件。
2. 对已知路径运行 `make feature-context TARGET=<path>`，以 manifest 解析 AppRoot/L1/L2/L3、DEC/REQ/GWT、OPEN、适用 AGENTS 和 profiles。
3. 明确 In Scope / Out of Scope、用户价值、验收意图、直接依赖、共享写点和最小后继工作流。默认不派 Reviewer。

- 执行中：`decision_request` / `concept_intake` / `$route`。

`$route` 表示按当前决定责任动态路由；Skill 不复制 envelope schema，所有可见输出统一由 canonical projector 生成。

## 完成证据

交付唯一 owner chain、canonical contexts/锨点、范围、验收层、风险与建议下游。证据是当前 manifest、Git 快照和引用的规格锨点，不是对话印象。

- POST：`completion_report` / `concept_intake` / `engineering_delivery_owner`。

## 失败与停止

无 owner、多 owner、父链断裂、验收意图缺失或发现未授权并行写入时返回 typed `GATE_BLOCK`，不向 prd/design/dev 猜测前进。

## 条件性交接

六类触发（跨会话未完成、多人并行、环境/发布、外部阻断、证据复用、用户显式要求）统一调用 canonical handoff producer；普通闭环不落持久交接。
