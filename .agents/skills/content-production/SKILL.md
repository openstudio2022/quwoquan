---
name: content-production
description: Run or resume the six-step Data producer workflow - init, acquire, author, review, publish, release - from a topic to canonical 趣我圈 objects and an immutable milestone handoff.
metadata:
  kind: workflow
---

# content-production

为用户愿意去的地方生产 homepage/article/image/video 四载体。宿主 AI 拥有来源选择、理解、创作、评审与调度；脚本只做摘要、探测、schema 与 create-once 封存，不出网、不作语义裁决、不推进或恢复步骤。

```text
init -> acquire -> author -> review -> publish -> release
```

按需加载：[六步与硬门](references/steps.md)、[载体差异](references/carriers.md)、[来源与取证](references/sourcing.md)、[可重建 recipes](references/recipes.md)（一次性脚本只在 `/tmp/qwq_rNN/`）、[记录型评分](references/quality.md)、[轮次与收官](references/rounds.md)、[里程碑 handoff](references/handoff.md)。

## 触发与输入

- 新任务先澄清一次，之后不再打断。必须落定的决定闭集：创作主体（creator persona 与 `creatorProfileId`）、地域与主题范围、里程碑目标与四载体配比、单轮实体数与并行轮数、单轮放弃比例上限与连续零净增停机轮数、随体媒体落盘与备份位置、需要用户明确授权的动作（提交、`release finalize`）。用宿主的提问能力一次问清；未答项采用 [rounds.md](references/rounds.md) 的声明式默认值并把假设逐条写进收官报告，不静默替用户决定。只有约束改变才重新澄清。
- 实体是用户愿意去的地方，不限 A 级或数量；类型只取 taxonomy `Entity/地点/*` 现有叶子。
- 实体产出配比：一个实体默认产 1 homepage + 1 article（换角度）+ 1–2 image（配图丰富时产 2 件）+ video（能落到该实体时）。homepage 主源必须是百科闭集（zh.wikipedia 或头条百科）；article 以实体条目换角度或主题条目为主源，游记等只作事实参考；image 与 video 的主源就是那一个文件页/作品页。不做数量推断、不做刻意剔重。
- 澄清完成后由宿主自己产出 plan 与 todos 并调度到终止条件；本 Skill 不定义调度器、状态机或轮次台账。
- 恢复：「已存在什么」只读 `release pool-query`；「在飞 execution 到哪一步」只读 `.qwq_output/data/tasks/<executionId>/_shared/receipts/` 的首个未闭合步骤；本会话在飞状态只活在宿主 todos。任一 receipt `blocked` 则以 `retryOf` 新建 execution，不在原 execution 回退；已有 receipt 或 reviewer 产物的工作单元不得再次派发。
- 产生 `content-release` 时，PRE 运行 `make feature-context TARGET=<exact-path>` 保存 content-addressed immutable owner manifest exact ref；纯只读且无送审交付只允许 `report-only/no-review-deliverable`。

## 执行

actor 契约：

- **主会话 owner**：与用户澄清、收官，直接完成 init、acquire、author、publish、release 与全部机械命令，不把任何步骤委托给通用子 Agent（`task init`、`task acquire`、`task seal`、`release publish-object`、`release finalize`、`release handoff-verify`、`release pool-query` 只在主会话执行）；只有 author 与 reviewer 两类独立语义 actor 可被派发，派发前先以 canonical artifact（receipt、`4.draft`、`reviews`）去重，已有 receipt 或 reviewer 产物的工作单元不得再次派发。
- **author**：一个 execution 恰有一个 author actor，可以是主会话，也可以是宿主派发的独立会话；一次调用负责该 execution 全部对象的 acquire 出网取证与 `4.draft` 产物。不同 execution 的 author 可并行。
- **reviewer**：每个 execution 由另一个真实会话评审，与本 execution author 的 `host/sessionId` 与 `invocation.runId` 必须不同，可为同一 model family；全局同一时刻至多一个 reviewer 调用，始终前台。reviewer 只写 execution 级 `reviews` 判断字段（含只记录的 `qualityScores`），不派发子 Agent、不改产物、不 seal、不 publish。`starting up` 不是进度也不是失败，不得据此补发相同或替代调用；中断后找首个未闭合步骤继续。

只有 acquire 的 AI 可出网，按 [sourcing.md](references/sourcing.md) 取证来源/license/作者/摘要、落正文与媒体、看图申报水印。robots/ToS 只记录，不规避登录墙、付费墙、验证码、DRM 或反爬挑战。同站串行并遵守 Crawl-delay，429/503 退避且放弃同轮余下候选。正文、caption、script、review、评分、typed issue、verdict、cohort、milestone 与人物/文章角度均由 AI 决定。

## 完成证据

硬门只有五条：来源 `sourceUrl/directUrl` 为 `https://` 且申报 `sha1`（有则）与本地字节一致；bytes 与 sha256 精确；权利字段（`sourceUrl/license/licenseUrl/creator`）在场——license 只记录并派生 `rightsStatus`，不阻断；author 与 reviewer 是不同 session/runId；对象身份唯一且 create-once；显式 cohort 且四载体计数不低于里程碑目标。水印、文风、结构、长度、配图率、质量评分、热度、权利疑虑只写 advisory 或记录字段，不阻断。`002-4.draft` seal 逐对象校验产物，违规对象只以 typed issue 退轮，至少一个合规产物即 `pass`。

producer 完成 = 三份 seal receipt 连续闭合 + 逐对象 publish 事务 + `release finalize` 产生的 immutable handoff（含 `producerBaselineRevision` 与 `producerContractDigest`，并把 `cohort.json`/`producer_release_handoff.json` 复制到受版本控制的 `quwoquan_data/reference/releases/<releaseId>/`）。release 不携带类别或命名就绪轨道，默认公开交付，保留真实权利记录；环境差异由下游显式环境配置表达，不属于 producer。M1/M10/M100/M1000 按累计唯一 finalized 对象计数，凡已完成 canonical publish 且 review approved 的对象都可进入 cohort。

内容池耐久性与代码同等重要：每轮收官后按 `commit` Skill 提交 `quwoquan_data/publish/**` 与随体清单（用户已授常设授权的前提下），并把随体媒体根 rsync 到用户指定的备份路径；`.qwq_output/**` 随时可删，`quwoquan_data/publish/**`、`quwoquan_data/reference/releases/**`、content library 与随体根不可删。

收官按 [rounds.md](references/rounds.md) 六段报告：目标与 `pool-query` 四载体计数、新增/复用数、逐条放弃原因及处置、blocked execution 首阻断、缺口、下轮最小入口，并附评分分布。缺段即未完成；计数不凭记忆。

## 失败与停止

按 [rounds.md](references/rounds.md) 分层处置：候选不合格则换来源；单对象违规则 typed 退轮、其余继续；身份/create-once/摘要或 seal 链断裂使 execution `blocked`，只能新建 `executionId + retryOf`；四载体数量不足记目标缺口，不冒充完成。

终止条件闭集，命中任一即收官：`pool-query` 四载体计数达约定目标；候选前沿耗尽；连续 N 轮净增为零（说明方法失效，换方法而不是硬跑）；用户中止或撞上授权闸口。单轮放弃比例超过上限即停轮报告。不手改门禁、不伪造证据、不回写旧 receipt。环境 import/activate/readback、App/API UAT、EAF、promotion/rollback 全部 out of scope；下游 owner 是 Environment Ops scheduler，本 Skill 不调度也不记录任何 consumer facts。

## 条件性交接

收官后不发明新恢复轨：缺口交 `plan-next` 生成最小下一轮，未完 execution 交 `continue` 从 receipts 续，送审交 `review`，提交交 `commit`，反复出现的教训交 `distill`；多次会话续跑是常态路径。产生 `content-release` 时，POST 把 PRE owner identity ref 原样作为 `--owner-identity`、current candidate evidence 作为 `--candidate-evidence` 调用 Review（workflow=`content-production`、deliverable=`content-release`），registry 只派一名 reviewer。`release finalize` 成功即 producer `END`，handoff 只含 release/cohort/canonical identity facts。源码/spec 变更走 Feature workflow。
