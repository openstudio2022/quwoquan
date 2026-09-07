---
name: content-production
description: Run or resume the six-step Data producer workflow - init, acquire, author, review, publish, release - from a topic to canonical 趣我圈 objects and an immutable milestone handoff.
metadata:
  kind: workflow
---

# content-production

目标只有一句：找到主题相关的公开原文（实体条目、文章、图片、视频），适度润色，加工成可在趣我圈展示的对象。宿主 Cursor/Codex Agent 是唯一语义主体，用自己的原生能力（检索、读页、终端、看图、子 Agent、规划）完成一切需要理解或看见的事；仓库脚本只做换任何人执行结果都相同且不可伪造的机械动作（算摘要、探测、按预算派生、校 schema、原子写入、create-once 封存）。脚本不出网、不选来源、不判相关性、不创作、不评审、不推进步骤、不恢复。

```text
init -> acquire -> author -> review -> publish -> release
```

每步的 AI 产出、脚本动作与唯一硬门见 [references/steps.md](references/steps.md)；四载体差异见 [references/carriers.md](references/carriers.md)；轮次、失败处置与收官见 [references/rounds.md](references/rounds.md)；里程碑 handoff 见 [references/handoff.md](references/handoff.md)。

## 触发与输入

- 新任务先澄清一次，之后不再打断。必须落定的决定闭集：创作主体（creator persona 与 `creatorProfileId`）、地域与主题范围、里程碑目标与四载体配比、单轮实体数与并行轮数、单轮放弃比例上限与连续零净增停机轮数、随体媒体落盘位置、需要用户明确授权的动作（提交、`release finalize`）。用宿主的提问能力一次问清；未答项采用 [rounds.md](references/rounds.md) 的声明式默认值并把假设逐条写进收官报告，不静默替用户决定。只有约束改变才重新澄清。
- 载体由来源单一类型判定：可命名的地点/机构/景区/博物馆条目 → homepage（最优先）；非单一实体的主题、线路、事件、文化现象条目 → article；Commons 图片文件页 → image；Commons 视频文件页 → video。一个来源只产一个对象，不做数量推断、不做刻意剔重。
- 澄清完成后由宿主自己产出 plan 与 todos 并调度到终止条件；本 Skill 不定义调度器、状态机或轮次台账。
- 恢复：「已存在什么」只读 `release pool-query`；「在飞 execution 到哪一步」只读 `.qwq_output/data/tasks/<executionId>/_shared/receipts/` 的首个未闭合步骤；本会话在飞状态只活在宿主 todos。任一 receipt `blocked` 则以 `retryOf` 新建 execution，不在原 execution 回退；已有 receipt 或 reviewer 产物的工作单元不得再次派发。
- 产生 `content-release` 时，PRE 运行 `make feature-context TARGET=<exact-path>` 保存 content-addressed immutable owner manifest exact ref；纯只读且无送审交付只允许 `report-only/no-review-deliverable`。

## 执行

actor 契约：

- **主会话**：与用户澄清、执行全部机械命令（`task init`、`task acquire`、`task seal`、`release publish-object`、`release finalize`、`release handoff-verify`、`release pool-query`）、派发子 Agent、收官。
- **author**：一个 execution 恰有一个 author actor，可以是主会话，也可以是宿主派发的独立子 Agent 会话；它拥有该 execution 全部对象的 acquire 出网取证与 `4.draft` 产物。不同 execution 的 author 可并行。
- **reviewer**：每个 execution 由另一个真实会话评审，与本 execution author 的 `host/sessionId` 与 `invocation.runId` 必须不同，可为同一 model family；同一 execution 同时至多一个 reviewer 调用，不同 execution 的 reviewer 可并行。reviewer 只写 execution 级 `reviews` 判断字段，不改产物、不 seal、不 publish。`starting up` 不是进度也不是失败，不得据此补发相同或替代调用。

出网只在 acquire 且只由 AI 做：检索条目与 Commons 文件页、逐字抄下 license/作者/`sha1`/说明、`curl` 下载、亲笔 `source.md`、看图申报水印三字段；同一来源站点串行、固定间隔、遇 429 退避，并行子 Agent 不得同时打同一站点，违规按轮次失败处理而不是重试。正文、caption、video script、评审、typed issue、verdict、cohort、milestone、来源是否切题、素材是否值得用、文章结构与作者人设一律由 AI 决定。

## 完成证据

硬门只有五条：来源 `sourceUrl/directUrl` 为 `https://` 且申报 `sha1` 与本地字节一致；bytes 与 sha256 精确；权利字段（`sourceUrl/license/licenseUrl/creator`）在场——license 只记录并派生 `rightsStatus`，不阻断；author 与 reviewer 是不同 session/runId；对象身份唯一且 create-once；显式 cohort 且四载体计数不低于里程碑目标。水印、文风、结构、长度、配图率、评分、权利疑虑只写 advisory 或记录字段，不阻断。

producer 完成 = 三份 seal receipt 连续闭合 + 逐对象 publish 事务 + `release finalize` 产生的 immutable handoff（含 `producerBaselineRevision` 与 `producerContractDigest`）。release 只有一个类别 `production`，媒体公开交付；未授权内容是否对公众开放由下游运营运行时配置决定，不属于 producer。M1/M10/M100/M1000 按累计唯一 finalized 对象计数，凡已完成 canonical publish 且 review approved 的对象都可进入 cohort。

一轮结束或命中终止条件时必须产出六段收官报告（见 [rounds.md](references/rounds.md)）：目标 vs `pool-query` 实际四载体计数、本次新增与复用对象数、放弃清单（逐条 + 原因码 + 处置）、blocked execution 及其首个 typed blocker、未闭合缺口、下一轮最小入口。任一段缺失即收官未完成；计数只从 `pool-query` 读，不从记忆读。

## 失败与停止

放弃而不阻塞。失败分四层，各有唯一处置：候选级（条目不存在、消歧义、正文过薄、水印是平台/图库标识、图与实体无关）换候选，零成本放弃且不落台账；对象级（ingest 失败、review rejected、publish 闭包失败）该对象退出本轮、execution 继续，短缺写进 typed issue，receipt 仍 `pass`；execution 级（create-once 冲突、字节漂移、author 与 reviewer 同 session/runId、seal 链断）该 execution `blocked`，其余不受影响，补齐只能以 `executionId + retryOf` 新建；目标级（四载体计数不达标）不是失败而是账，进收官报告缺口，绝不当作完成。

终止条件闭集，命中任一即收官：`pool-query` 四载体计数达约定目标；候选前沿耗尽；连续 N 轮净增为零（说明方法失效，换方法而不是硬跑）；用户中止或撞上授权闸口。单轮放弃比例超过上限即停轮报告。不手改门禁、不伪造证据、不回写旧 receipt。环境 import/activate/readback、App/API UAT、EAF、promotion/rollback 全部 out of scope；下游 owner 是 Environment Ops scheduler，本 Skill 不调度也不记录任何 consumer facts。

## 条件性交接

收官后不发明新恢复轨：缺口交 `plan-next` 生成最小下一轮，未完 execution 交 `continue` 从 receipts 续，送审交 `review`，提交交 `commit`，反复出现的教训交 `distill`；多次会话续跑是常态路径。产生 `content-release` 时，POST 把 PRE owner identity ref 原样作为 `--owner-identity`、current candidate evidence 作为 `--candidate-evidence` 调用 Review（workflow=`content-production`、deliverable=`content-release`），registry 只派一名 reviewer。`release finalize` 成功即 producer `END`，handoff 只含 release/cohort/canonical identity facts。源码/spec 变更走 Feature workflow。
