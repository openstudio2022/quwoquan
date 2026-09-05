# quwoquan_data Agent Guide

在 `quwoquan_data/` 工作时，除仓库根 `AGENTS.md` 外先阅读 `quwoquan_data/README.md`。

## Data 内容生产边界

`.agents/skills/content-production/SKILL.md` 是 Data producer 九阶段的唯一流程真相源；本文件只约束工程边界，不复制阶段正文。producer 从冻结 demand 运行到 immutable `release` handoff 即结束。环境 import/activate/readback/health、API/App UAT、EAF、promotion、rollback 与 replay 由下游环境 owner 并行执行，不是 content-production Skill 的阶段或完成条件。

宿主 AI 直接读 OPEN 冻结上下文、选择来源与素材、做质量判断与 compose、写 homepage/article 正文、image caption/work、video script、逐对象 self-check 与独立 review，并显式提交 `actor/verdict/typedIssues/resultRefs/verifierFacts`、approved 对象、explicit cohort 与 milestone。代码不得决定业务阶段、来源、内容、review、verdict、typed issue、approved、cohort、milestone、后继或恢复。

代码允许边界只有：

- `task init` 原子创建三份工作包输入；
- `task stage-open` 冻结 AI 点名的 exact input refs；
- `task stage-close` 重验 exact bytes/schema/verifier facts 并 create-once 写 receipt；
- atomic download 与媒体 CAS；
- schema、digest、ref、media hard facts verify；
- approved 单对象 `publish-object` 与 explicit cohort `pool-build` 原子 I/O。

批量并发、限流、reviewer session 编排、会话重启与排队属于宿主 runtime，不进入仓内状态。禁止保留或新增 stage-gate registry、semantic prepare/record wrapper、runner/fleet/lane claim、agent/controller/queue/campaign/recovery、自动恢复、execution-state reducer、managed SDK/provider、第二 registry/processor/脚本。旧 sequence-017 不修、不迁、不兼容；任何旧轨引用、import、CLI、schema、fixture、test 与文档必须在物理删除增量中归零，不得用 shim 或 dual-read 保留。

既有 `ship` CLI/环境实现保留给下游环境 owner；不得删除，也不得继续把它登记为 producer stage 或 producer receipt。producer stage enum/schema/test expectation 与完整 release HANDOFF schema 已硬切为九阶段 terminal contract；后续 fresh M1 仅用于补齐真实证据，不代表实现缺失。

新能力优先进入 `python3 quwoquan_data/scripts/cli.py <command>` 的现有边界，不新增可直接运行的业务脚本。schema、metadata、taxonomy 与内容契约先行。脚本不得拼正文、image caption、video script、rubric、rights 结论或 attestation。

## 内容与证据

- 两条供给线均需闭合：内容稿件（homepage/article/image/video 等）与 entity/tag/media/rights 治理。
- `sources` 只写每 target 的来源计划，不物化 source unit；`1.download` 才按计划生成 source units、source refs 与 CAS holdings。
- `3.compose` 的选材由 AI 完成；`4.draft` 必须有载体正文对象、draft meta、self-check 与 agent result envelope；`5.review` 由独立 AI 逐对象写 rubric、reviewer、media、rights 与 attestation，禁止脚本合成。
- homepage 正文底稿仅允许 Wikipedia、百度百科公开词条、今日头条百科；结构化事实可额外使用官网与政府/文旅门户，并逐字段保留 `factSources`。OTA、聚合门户与媒体不得伪装为正文主证据。
- 不可追溯 source、rights、creator/tag/entity/media identity 或 review 结论不得 publish。
- approved 对象由 AI 逐个调用单对象事务；release cohort 与 milestone 必须显式，禁止 all-publishable。

## Producer 完成与下游 handoff

producer 完成只绑定连续九阶段 receipts 与 immutable release HANDOFF。HANDOFF required contract 固定包含 release ref/digest、explicit cohort ref/digest、milestone、四载体 counts、content-pool handoff refs/digests 与 producer baseline revision。terminal handoff 必须在所有 execution 的 sequence-009/pass 后 create-once 成功，且绑定完整 receipt 链、explicit cohort 与 producer baseline revision；没有 handoff 时不得宣称 producer END。

下游环境 owner 只读该 handoff 执行现有 `ship`/Ops 能力。任何环境结果都不能回写 producer receipt、改变 cohort/release bytes，或成为“内容生产完成”的门槛。涉及环境实现时另读 `quwoquan_ops/AGENTS.md`。

## 工程卫生

`.qwq_output/` 仅放可删除重建的运行产物、证据与缓存。控制面真相源不得写入 output。Python bytecode、pytest cache 与工具缓存按仓库既有隔离规则落盘；禁止在仓库根创建临时脚本。不要运行长门禁，按改动范围执行短静态检查或文档引用检查。
