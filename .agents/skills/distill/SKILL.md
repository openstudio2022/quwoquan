---
name: distill
description: Turn recurring cross-session lessons into structured rule candidates - collect repeated gaps from handoff manifests, recurring review findings, or a second same-type user correction, then propose candidates with trigger scenario, root-cause layer, landing spot, and gate/check binding for human confirmation before prd/dev landing. Use when the user says 沉淀规则, 教训沉淀, 规则候选, or when the same lesson recurs across rounds.
metadata:
  kind: workflow
---

# distill

## 触发与输入

同类用户纠正第二次出现、Review finding 跨轮复发、或持久交接中同类 gap 反复时触发。输入必须是可引用的多次证据，不是单次偏好。

自然语言触发与显式 Skill 调用同轨，字段、闭集与审计隔离只引用 `quwoquan_ops/policies/human_agent_delivery_contract.yaml#workflow_interaction_binding.distill`：

- PRE：`progress_update` / `feedback_knowledge_distillation` / `engineering_delivery_owner`。

## 执行

1. 去重并引用复发实例，区分现象、根因层和可自动判定的输入。
2. 每个候选声明触发场景、MUST/MUST NOT、唯一 owner 层和可执行 gate/check/evidence 绑定。落点只能是根全局不变量、子树稳定不变量、Workflow Skill、Feature spec/design/contracts 或 Review checklist 视角；不用 role reference 承载规范。
3. 候选先交人确认，不直接改规则/规格/gate。已确认候选交 prd/design/dev 正常落地。
4. POST 只在用户需要准出时调 `review`，主审为 Architect，至多一名专审。

- 执行中：`decision_request` / `feedback_knowledge_distillation` / `$route`。

`$route` 表示按当前决定责任动态路由；Skill 不复制 envelope schema，所有可见输出统一由 canonical projector 生成。

## 完成证据

交付去重候选及其复发证据、根因层、唯一落点、可执行绑定和人工裁决状态。未获确认不称为已落地。

- POST：`completion_report` / `feedback_knowledge_distillation` / `$route`。

## 失败与停止

只有单次事件、无可引用证据、owner 不唯一或无可执行判据时停止沉淀，作为 advisory 返回。候选未经人确认时禁止自动修改。

## 条件性交接

六类触发（跨会话未完成、多人并行、环境/发布、外部阻断、证据复用、用户显式要求）统一调用 canonical handoff producer；普通闭环不落持久交接。
