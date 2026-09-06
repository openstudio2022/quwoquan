# quwoquan_data Agent Guide

在 `quwoquan_data/` 工作时，除仓库根 `AGENTS.md` 外先阅读 `quwoquan_data/README.md`。

## Data 内容生产边界

`.agents/skills/content-production/SKILL.md` 是 Travel Research Data producer 九阶段的唯一流程真相源；本文件只约束工程边界，不复制阶段正文。producer 从冻结 demand 运行到 immutable `release` handoff 即结束。import/activate/readback/health、API/App UAT、EAF、sampling authority、promotion、rollback 与 replay 全部 out of scope，不进入 handoff、恢复或完成条件。

宿主 Cursor/Codex Agent 是唯一语义主体，直接读 OPEN 冻结上下文、选择来源与素材、做质量判断与 compose、写唯一 carrier draft、完成 self-check 与独立 `content_review.json`，并显式提交 `actor/verdict/typedIssues/resultRefs/verifierFacts`、approved 对象、explicit cohort 与 milestone。代码不得决定业务阶段、来源、内容、review、verdict、typed issue、approved、cohort、milestone、后继或恢复。

代码允许边界只有：

- `task init` 从只冻结目标对象身份的 candidate bindings 原子创建三份工作包输入，不要求 pre-init source/media admission；
- `task stage-open` 冻结 AI 点名的 exact input refs；
- `task stage-close` 重验 exact bytes/schema/verifier facts 并 create-once 写 receipt；
- atomic download 与媒体 CAS；
- schema、digest、ref、media hard facts verify；
- approved 单对象 `publish-object` 与 explicit cohort `pool-build` 原子 I/O。

不同 execution 的并发、限流、会话派发、重启与排队属于宿主 runtime，不进入仓内状态。同一 execution 的 `4.draft` 全部对象只由一个 author 会话负责，`5.review` 全部对象只由另一个 reviewer 会话负责。禁止保留或新增 resolver/projector/runner/controller/queue/registry/SDK、actor projection、stage-gate、自动恢复或 execution-state reducer。旧 sequence-017 不修、不迁、不兼容；任何旧轨引用、import、CLI、schema、fixture、test 与文档必须在物理删除增量中归零，不得用 shim 或 dual-read 保留。

既有 consumer/environment 实现不在本任务范围内；不得把它登记为 producer stage、receipt 或完成条件。当前 Python/schema/tests 仍需后续按本轮 authoring source 硬切，不得反向把现状视为规格真相。

新能力优先进入 `python3 quwoquan_data/scripts/cli.py <command>` 的现有边界，不新增可直接运行的业务脚本。authoring source 先行。脚本不得拼正文、image caption、video script、`content_review.json`、rights 结论、typed issue 或 verdict。

## 内容与证据

- 两条供给线均需闭合：内容稿件（homepage/article/image/video 等）与 entity/tag/media/rights 治理。
- candidate binding 只冻结目标对象身份；`sources` 只写每 target 的来源计划，`1.download` 才按计划取得 bytes、生成 source units/source refs/CAS 与机械 hard facts，不要求 `source.clean.md|source.layout.json|source.quality.json`。
- `2.quality` 作语义保留，`3.compose` 选材与结构；`4.draft` 每对象只留一个 carrier 主产物，self-check 与 author/invocation/digests 由 sequence-006 receipt 冻结；`5.review` 每对象只留一份 `content_review.json`，reviewer/invocation/digest 由 sequence-007 receipt 冻结。
- homepage 正文底稿仅允许 Wikipedia、百度百科公开词条、今日头条百科；结构化事实可额外使用官网与政府/文旅门户，并逐字段保留 `factSources`。OTA、聚合门户与媒体不得伪装为正文主证据。
- 不可追溯 source、rights、creator/tag/entity/media identity 或 review 结论不得 publish。
- approved 对象由 AI 逐个调用单对象事务；release cohort 与 milestone 必须显式，禁止 all-publishable。

## Producer 完成与下游 handoff

producer 完成只绑定连续九阶段 receipts 与 immutable release HANDOFF。M1/M10/M100/M1000 按 `cumulative_unique_finalized_objects` 计数，每级形成自己的 full explicit cohort/release/handoff，复用对象绑定原 execution/publish proof而不伪造 receipts。HANDOFF 只含 release/cohort/milestone/counts/content-pool/proof/baseline producer facts。terminal handoff 必须在所有 execution 的 sequence-009/pass 后 create-once 成功，且绑定完整 receipt 链、explicit cohort 与 producer baseline revision；没有 handoff 时不得宣称 producer END。

HANDOFF 不含 UAT/sample authority/import/activate/readback、App/API UAT、EAF、environment promotion 或 rollback。任何外部 consumer 结果都不能回写 producer receipt、改变 cohort/release bytes，或成为“内容生产完成”的门槛。

## 工程卫生

`.qwq_output/` 仅放可删除重建的运行产物、证据与缓存。控制面真相源不得写入 output。Python bytecode、pytest cache 与工具缓存按仓库既有隔离规则落盘；禁止在仓库根创建临时脚本。不要运行长门禁，按改动范围执行短静态检查或文档引用检查。
