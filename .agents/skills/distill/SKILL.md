---
name: distill
description: Turn recurring lessons (repeated handoff gaps, recurring review findings, a second same-type user correction) into rule candidates with trigger, root-cause layer, landing spot and gate binding for human confirmation. Use when the user says 沉淀规则, 教训沉淀, 规则候选, or a lesson recurs across rounds.
metadata:
  kind: workflow
---

# distill

## 触发与输入

同类用户纠正第二次出现、Review finding 跨轮复发或持久交接中同类 gap 反复时触发。输入是可引用的复发实例、handoff/review evidence 与人工反馈；保持这些原生输入，不把中央 resolver 设为前置。

## 执行

1. 去重并引用复发实例，区分现象、根因层和可自动判定输入；同类坏味道必须至少有两个独立实例，单次 finding 只保留 advisory。
2. 每个候选声明触发场景、MUST/MUST NOT、唯一 owner 层与既有或新增 deterministic gate/check/evidence 绑定；落点只允许根/子树不变量、Workflow Skill、Feature spec/design/contracts 或 Review checklist。
3. 候选先交人确认，不直接改规则/规格/gate；已确认候选再交 prd/design/dev 落地。
4. POST 默认零 Reviewer。

## 完成证据

交付去重候选、复发证据、根因层、唯一落点、可执行绑定与人工裁决状态；未获确认不称已落地。

## 失败与停止

只有单次事件、无可引用证据、owner 不唯一或无可执行判据时停止沉淀并返回 advisory；不为满足流程伪造第二样本。

## 条件性交接

人确认后按落点交 prd/design/dev。持久交接语义见 continue Skill。
