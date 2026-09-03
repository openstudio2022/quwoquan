---
name: distill
description: Turn recurring cross-session lessons into structured rule candidates - collect repeated gaps from handoff manifests, recurring review findings, or a second same-type user correction, then propose candidates with trigger scenario, root-cause layer, landing spot, and gate/check binding for human confirmation before prd/dev landing. Use when the user says 沉淀规则, 教训沉淀, 规则候选, or when the same lesson recurs across rounds.
metadata:
  kind: workflow
---

# distill

## 触发与输入

同类用户纠正第二次出现、Review finding 跨轮复发或持久交接中同类 gap 反复时触发。输入是可引用的复发实例、handoff/review evidence 与人工反馈；保持这些原生输入，不把 owner manifest 或中央 resolver 设为前置。角色交互只引用 `quwoquan_ops/policies/human_agent_delivery_contract.yaml#workflow_interaction_binding.bindings.distill`，可见输出由 canonical projector 生成。

## 执行

1. 去重并引用复发实例，区分现象、根因层和可自动判定输入。
2. 每个候选声明触发场景、MUST/MUST NOT、唯一 owner 层与 gate/check/evidence 绑定；落点只允许根/子树不变量、Workflow Skill、Feature spec/design/contracts 或 Review checklist。
3. 候选先交人确认，不直接改规则/规格/gate；已确认候选再交 prd/design/dev 落地。
4. POST 仅在用户要求准出时按 review Skill 执行。

## 完成证据

交付去重候选、复发证据、根因层、唯一落点、可执行绑定与人工裁决状态；未获确认不称已落地。

## 失败与停止

只有单次事件、无可引用证据、owner 不唯一或无可执行判据时停止沉淀并返回 advisory；不为满足流程伪造第二样本。

## 条件性交接

人确认后按落点交 prd/design/dev；只有 canonical 六类 handoff 触发成立时持久交接。
