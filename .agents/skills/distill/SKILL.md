---
name: distill
description: Turn recurring cross-session lessons into structured rule candidates - collect repeated gaps from handoff manifests, recurring review findings, or a second same-type user correction, then propose candidates with trigger scenario, root-cause layer, landing spot, and gate/check binding for human confirmation before prd/dev landing. Use when the user says 沉淀规则, 教训沉淀, 规则候选, or when the same lesson recurs across rounds.
metadata:
  kind: workflow
---

# distill

把跨会话重复出现的教训转成**结构化规则候选**，经人确认后走 prd/dev 正常工作流落地。
本工作流只产出候选与提议，**不直接修改任何规则资产**——回写权在人确认之后的
prd/dev。五段执行契约见根 `AGENTS.md`。

## 触发

以下任一信号出现即触发（自动或由用户点名）：

- 轮次交接单出现跨轮重复缺口（同一问题在两个及以上轮次的缺口段出现）。
- 评审同类 finding 复发（同根因的 finding 在两次及以上评审中出现）。
- 用户同类纠正第二次出现（同一类行为被用户纠正两次）。
- 自然语言：沉淀规则、教训沉淀、规则候选。

## 输入

- 历史轮次交接单（`.qwq_output/env/repo/runs/handoff/*/manifest.md`）的缺口段。
- 评审产物（`.qwq_output/env/repo/runs/review/*/`）中的 finding。
- 既有候选清单（`.qwq_output/env/repo/runs/distill/`，若存在则增量更新而非重建）。
- 用户纠正的原话或会话上下文。

## 角色

主会话扮演 **distiller**（沉淀者）：归纳、判层、提议；不裁决、不落地。

## 执行

自由度：中（候选结构固定，归纳自由）。

1. **证据归组** — 把复发信号按根因归组；每组必须有两次及以上独立出现的证据
   （轮次、评审或会话标识）。单例不成候选。
2. **泛化判定** — 每组按 plan-next 的「孤例还是一类」判定给出排查范围；
   判为一类的候选必须写明系统性排查方式（全仓扫描 / gate 化 / 棘轮化）。
3. **候选成文** — 每条候选固定四字段：
   - 触发场景：什么情境下该规则生效。
   - 根因层：`prompt 指令 / 规则资产 / 门禁 / 结构性缺陷` 四选一。
   - 建议落点：AGENTS.md、checklist、reference、gate、spec 节点之一（唯一 owner，
     不与既有资产重复正文）。
   - gate/check 绑定：绑定真实 gate 命令或客观 check 谓词；**无绑定的候选
     只能落 SHOULD / ADVISORY，不得标 MUST**。
4. **提议与确认** — 候选清单落 `.qwq_output/env/repo/runs/distill/`，向用户
   呈现并请求逐条裁决（采纳 / 降级 / 拒绝 / 挂起）。
5. **移交落地** — 已确认候选交 prd（需改规格）或 dev（改 checklist/gate）承接；
   候选清单更新状态与落地位置。

[MUST NOT] 绕过人确认直接修改 AGENTS.md、SKILL.md、checklist、reference 或 gate。
[MUST NOT] 把候选清单当第二真相源——落地后的规则以资产本身为准，清单只记状态。

## 交付件

**规则候选清单**：带四字段与状态（待确认 / 已确认待落地 / 已落地 / 已拒绝）的
候选集合，落 `.qwq_output/env/repo/runs/distill/`。

送审前自检：

- 每条候选有两次及以上独立复发证据；
- 无绑定候选未标 MUST；
- 落点无重复正文。

## 内置评审

- POST：调 `review`（workflow=`distill`，segment=POST，deliverable=`rule-candidates`），
  典型角色 architect + user，校验落点唯一、绑定真实、证据可追溯。

## 失败与停止

候选缺复发证据、落点与既有资产重复正文、或本轮 diff 出现未经确认的规则资产
变更时返回 `GATE_BLOCK`，不得宣称沉淀完成。

## HANDOFF

- **完成判据**：见 [completion-criteria](../review/references/completion-criteria.md) 本工作流段。
- **产出物**：规则候选清单与逐条裁决结果。
- **未决项去向**：未确认候选留清单挂起；被拒候选记拒绝理由；不允许悬空。
- **唯一合法下游**：`prd`（候选需改规格）或 `dev`（候选改 checklist/gate/reference）。
- **证据链**：候选引用的轮次/评审/会话证据标识，与 `make verify-agent-context-budget` 结果。
