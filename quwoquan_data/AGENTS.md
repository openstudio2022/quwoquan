# quwoquan_data Agent Guide

在 `quwoquan_data/` 工作时，除仓库根 `AGENTS.md` 外先阅读 `quwoquan_data/README.md`。

## Data 内容生产边界

`.agents/skills/content-production/SKILL.md` 是 Data producer 六步（init → acquire → author → review → publish → release）的唯一流程真相源；本文件只约束工程边界，不复制步骤正文。producer 从主题到 `release finalize` 的 immutable handoff 即结束。import/activate/readback/health、API/App UAT、EAF、sampling authority、promotion、rollback 与 replay 全部 out of scope，不进入 handoff、恢复或完成条件；下游 owner 是 Environment Ops scheduler（EAF v2 profile 闭集 `smoke|integration|release`），Data 不写 EAF。

宿主 Cursor/Codex Agent 是唯一语义主体：判定来源类型与载体、点名来源 URL 与相关性、创作唯一 carrier 产物、以另一个真实会话独立评审，并显式给出 approved 对象、explicit cohort 与 milestone。代码不得决定来源、相关性、内容、review、verdict、typed issue、approved、cohort、milestone、后继或恢复。

代码允许边界只有六条命令：

- `task init`：从 carrier demand 与 candidate bindings 原子创建 `execution_manifest.json`、`0.plan/request.json`、`0.plan/target_set.json`；
- `task acquire`：按 AI 点名的 URL 机械取得字节、sha256、license/作者/直链、mime/尺寸/时长与 poster，写 source unit 与 `1.download/source_refs.json`，媒体字节入 content library；
- `task seal`：校验当前步骤硬事实并 create-once 写 `001-1.download` / `002-4.draft` / `003-5.review` receipt；review seal 补齐 `content_review.json` 的机械字段（schema/stage/executionId/objectRef/draft 与 assetRights 权利转录）；
- `release publish-object`：对 approved 对象执行唯一一次原子 canonical 事务；
- `release finalize`：pool-build + release-integrity + create-once handoff（含 `producerBaselineRevision` 与 `producerContractDigest`）；
- `release handoff-verify`：只读重放。

两个 actor：主会话直接完成 init/acquire/author/publish/release 与全部机械命令；`5.review` 由另一个真实 reviewer 会话完成，全局至多一个前台 reviewer 调用。禁止 stage-open、宿主 verifierFacts、resolver/projector/runner/controller/queue/registry/SDK、actor projection、stage-gate、自动恢复或 execution-state reducer。任何旧轨引用、import、CLI、schema、fixture、test 与文档在物理删除增量中归零，不得用 shim 或 dual-read 保留。

新能力优先进入 `python3 quwoquan_data/scripts/cli.py <command>` 的现有边界，不新增可直接运行的业务脚本。authoring source 先行。脚本不得拼正文、image caption、video script、`content_review.json` 的判断字段、typed issue 或 verdict。

## 内容与证据

- 来源单一类型判定：可命名的地点/机构/景区/博物馆条目 → homepage；主题/线路/事件/文化现象条目 → article；Commons 图片文件页 → image；Commons 视频文件页 → video。一个来源只产一个对象，不做数量推断与刻意剔重。
- 硬门只有六条：来源 `https://` 可检索；bytes 与 sha256 精确；license 在研究白名单（CC0/CC BY/CC BY-SA/PD）且权利六字段在场；author 与 reviewer 是不同 session/runId；对象身份唯一且 create-once；显式 cohort 与里程碑计数。文风、结构、长度、配图率、评分等只作 advisory。
- `4.draft` 每对象只留一个 carrier 主产物（`page.md|draft.article.md|image_work.json|video_script.json`），标题/tagRefs/creatorProfileId 由产物自身声明；`5.review` 每对象只留一份 `content_review.json`，AI 只写判断字段。
- 商用级权利字段（modelRelease/propertyRelease/audioRights/commercialAuthorization/publicationAdmission）只在 `releaseClass=commercial` 时要求。
- approved 对象由 AI 逐个调用单对象事务；release cohort 与 milestone 必须显式，禁止 all-publishable。

## Producer 完成与下游 handoff

producer 完成 = 三份 seal receipt 连续闭合 + 逐对象 publish 事务 + `release finalize` 的 immutable handoff。M1/M10/M100/M1000 按 `cumulative_unique_finalized_objects` 计数，每级形成自己的 full explicit cohort/release/handoff；凡已完成 canonical publish 且 review approved 的对象都可复用进入 cohort，handoff 以 canonical publish proof 为凭，不内嵌 execution receipt 链。HANDOFF 只含 release/cohort/milestone/counts/content-pool identity/baseline/contract digest 等 producer facts。

HANDOFF 不含 UAT/sample authority/import/activate/readback、App/API UAT、EAF、environment promotion 或 rollback。任何外部 consumer 结果都不能回写 producer receipt、改变 cohort/release bytes，或成为“内容生产完成”的门槛。

## 工程卫生

`.qwq_output/` 仅放可删除重建的运行产物、证据与缓存；`data/local/` 下只允许 `cache/`、`runs/`、`workspace/`，本次 run 的输入与规划放 `data/local/workspace/<run>/`。控制面真相源不得写入 output。Python bytecode、pytest cache 与工具缓存按仓库既有隔离规则落盘；禁止在仓库根创建临时脚本。不要运行长门禁，按改动范围执行短静态检查或文档引用检查。
