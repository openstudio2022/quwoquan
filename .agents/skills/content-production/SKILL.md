---
name: content-production
description: Run or resume the six-step Data producer workflow—init, acquire, author, review, publish, release—from a topic to canonical 趣我圈 objects and an immutable milestone handoff.
metadata:
  kind: workflow
---

# content-production

宿主拥有语义与阶段推进；工具只做单阶段动作。publish 保存，release 冻结，环境装配归下游。

## 触发与输入

- 新任务一次确认范围、预算、停止、备份和动作授权；已有授权直接引用，范围变更才重确认。实体限 taxonomy `Entity/地点/*` 叶子；规模/WIP 只读 [session](references/session.md)。
- `content-release` PRE 运行 `make feature-context TARGET=<exact-path>`，保存 content-addressed immutable owner manifest exact ref；纯只读为 `report-only/no-review-deliverable`。
- 根规则→本 Skill→当前 [pipeline](references/pipeline.md)/[session](references/session.md)；按需读 [dispatch](references/dispatch.md)、[team](references/team.md)、[sourcing](references/sourcing.md)、[grok-team-rebuild](references/grok-team-rebuild.md) 与当前 carrier。
- Skill 根钉 data-engineering 工作树，`QWQ_PUBLISH_ROOT` 绑定独立内容仓；不混用 lane/tasks。实例资格只读 bootstrap/session；仅总监可 finalize/Git。

## 执行

1. **init**：冻结 identity/executionId，运行 `task init --round`。
2. **acquire**：宿主选源/看素材/申报事实；运行来源工具、零网络 `task acquire` 与 seal。
3. **author**：完成 execution 有效 resultRefs、author seal，整批交 QA。
4. **review**：独立 QA 自领 execution，写唯一 `seal.review.json`、review seal，整批交总监。
5. **publish**：总监逐个点名 approved 对象并 readback，先 homepage 后 post，不等其他批。
6. **release**：总监按授权及 explicit cohort/milestone/baseline finalize；Git 另需授权。

创作者就是本人 execution 的主会话；独立 QA review；总监唯一收官。每 execution 一 author、一独立 reviewer。多 author/QA 可并行不同小批；每作者最多两个未闭合批且最多一个创作，不设全团队两 author 或单 QA 串行限制。同 shard 仅不重叠 execution 写者；同 execution/review scope 单写，canonical 事务串行。

主会话保持 execution owner，派发前按 receipt/artifact 去重；actor 不嵌套派发、关闭阶段、建替代 execution 或 publish。`starting up` 不是进度/失败，不得补发；恢复先核终态并保留归属。引用 native host/sessionId/runId；不把语义交脚本，不包装 seal/publish 或建调度器。

## 完成证据

- 摘要、bytes/sha256、权利、独立 actor、schema/ref/create-once 与 cohort 计数须成立；其余如实记录。
- 完成 = 三份 seal receipt + 点名 publish + finalize handoff，绑定 baseline/contract、内容仓身份及 exact 快照；terminal 位于 `$QWQ_PUBLISH_ROOT/releases/<releaseId>/`。
- release 单链路；环境差异归下游。每轮按 [session 收官](references/session.md#收官) 报告六段、池 readback、exact refs 与未验证项；不自动清理在飞产物。

## 失败与停止

候选失败换源，对象失败退轮；execution 身份/闭包失败 blocked，仅 `retryOf` 新建。达到目标、前沿耗尽、连续零净增、超预算、中止或授权不足即收官；不规避访问挑战。

恢复读池/receipts，找首个未闭合步骤；已有 receipt 或 reviewer 产物不得再次派发。unknown 不释放 scope，不从 claim/聊天/daemon 推导完成。宿主不可达、挑战、429、磁盘不足记 `GATE_BLOCK`，停受影响范围。

## 条件性交接

缺口交 `plan-next`，未完交 `continue`，送审交 `review`，提交交 `commit`；源码/spec 变更回 Feature workflow。POST 用 `--owner-identity` 携带 PRE owner identity ref、`--candidate-evidence` 携带 current candidate evidence，registry 只派一名 reviewer。

finalize 即 producer END；环境验证、EAF、promotion/rollback/replay 由 Environment Ops 独立拥有。
