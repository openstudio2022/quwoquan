# quwoquan_data Agent Guide

在 `quwoquan_data/` 工作时，除仓库根 `AGENTS.md` 外先阅读 `quwoquan_data/README.md`。

## Data 内容生产边界

`.agents/skills/content-production/SKILL.md` 是 Data producer 六步（init → acquire → author → review → publish → release）的唯一流程真相源；本文件只约束工程边界，不复制步骤正文。producer 从主题到 `release finalize` 的 immutable handoff 即结束。import/activate/readback/health、API/App UAT、EAF、sampling authority、promotion、rollback 与 replay 全部 out of scope，不进入 handoff、恢复或完成条件；下游 owner 是 Environment Ops scheduler（EAF v2 profile 闭集 `smoke|integration|release`），Data 不写 EAF。

宿主 Cursor/Codex Agent 是唯一语义主体，用自己的原生能力（检索、读页、终端、看图、子 Agent、规划）判定来源类型与载体、出网检索取证下载、看图申报水印、创作唯一 carrier 产物、以另一个真实会话独立评审，并显式给出 approved 对象、explicit cohort 与 milestone。职责边界只按可伪造性划分：同样字节换任何执行者结果相同且不可伪造的归代码；需要理解语义或看见内容的归 AI。代码不得出网、不得决定来源、相关性、内容、review、verdict、typed issue、approved、cohort、milestone、后继或恢复。`quwoquan_data/scripts/content/source/**`、`content/execution/**` 与 `core/**` 不得存在任何 HTTP/socket 出网点（由 local_contract 静态门锁定）；环境回读的 `content/release/environment/public_api_client.py` 验证的是自家服务而非来源站点，不在此限。

代码允许边界只有六条命令，且每条都是单阶段、无状态、无恢复的展开：

- `task init --round`：从一份 round spec 为该轮每个 carrier 原子创建 `execution_manifest.json`、`0.plan/request.json`、`0.plan/target_set.json`；
- `task acquire --input <ingest.json>`：零网络 ingest——从 AI 已下载的本地字节算 sha256、按申报 sha1 交叉校验、探测 mime/尺寸/时长、按预算降采样/转码/抽 poster、按申报 license 派生 `rightsStatus`、转录水印三字段与真实 `derivedModifications`，写 source unit 与 `1.download/source_refs.json`，媒体字节入 content library；逐 target 独立报告；
- `task seal`：校验当前步骤硬事实并 create-once 写 `001-1.download` / `002-4.draft` / `003-5.review` receipt；`5.review` 从 execution 级 `reviews` 扇出逐对象 `content_review.json` 并补齐机械字段（schema/stage/executionId/objectRef/draft 与 assetRights 权利转录）；
- `release publish-object`：对 approved 对象执行唯一一次原子 canonical 事务；
- `release finalize`：pool-build + release-integrity + create-once handoff（含 `producerBaselineRevision` 与 `producerContractDigest`）；
- `release handoff-verify`：只读重放。

actor 契约：主会话拥有与用户澄清、全部机械命令、子 Agent 派发与收官；一个 execution 恰有一个 author actor（可为主会话或宿主派发的独立子 Agent 会话）；`5.review` 由另一个真实 reviewer 会话完成，与本 execution author 不同 session/runId，同一 execution 同时至多一个 reviewer 调用，不同 execution 可并行。禁止 stage-open、宿主 verifierFacts、resolver/projector/runner/controller/queue/registry/SDK、actor projection、stage-gate、自动恢复、execution-state reducer 或轮次台账。凡跨阶段推进、读 receipt 决定下一步、重试或恢复都属被禁的 runner。任何旧轨引用、import、CLI、schema、fixture、test 与文档在物理删除增量中归零，不得用 shim 或 dual-read 保留。

新能力优先进入 `python3 quwoquan_data/scripts/cli.py <command>` 的现有边界，不新增可直接运行的业务脚本，也不在 `.qwq_output/` 留不可从版本控制真相源重建的助手脚本。authoring source 先行。脚本不得拼正文、image caption、video script、`content_review.json` 的判断字段、typed issue 或 verdict。

## 内容与证据

- 来源单一类型判定：可命名的地点/机构/景区/博物馆条目 → homepage；主题/线路/事件/文化现象条目 → article；Commons 图片文件页 → image；Commons 视频文件页 → video。一个来源只产一个对象，不做数量推断与刻意剔重。
- 硬门只有五条：来源 `sourceUrl/directUrl` 为 `https://` 且申报 sha1 与本地字节一致；bytes 与 sha256 精确；权利字段（`sourceUrl/license/licenseUrl/creator`）在场（license 只记录并派生 `rightsStatus`：白名单 CC0/CC BY/CC BY-SA/PD → verified，其它可读 → unverified 并写 `rightsIssues`，不可读 → unknown；任何取值不阻断）；author 与 reviewer 是不同 session/runId；对象身份唯一且 create-once；显式 cohort 且四载体计数不低于里程碑目标。水印（`watermarkStatus/watermarkKind/watermarkNote` 由看过像素的 AI 申报，缺席只能记 unknown，`present` 汇总进 release header `watermarkedAssetIds`）、文风、结构、长度、配图率、评分、权利疑虑等只作记录或 advisory。文章配图张数不设下限。
- 放弃而不阻塞：候选级失败换候选；对象级失败该对象退轮、execution 继续、receipt 仍 `pass`；execution 级身份/完整性失败该 execution `blocked`，以 `retryOf` 新建补齐；四载体计数不达标是账不是失败。每轮收官六段报告（目标 vs `pool-query` 计数、新增/复用、放弃清单、blocked 与首个 typed blocker、缺口、下一轮入口），计数只从 `pool-query` 读。
- `4.draft` 每对象只留一个 carrier 主产物（`page.md|draft.article.md|image_work.json|video_script.json`），标题/tagRefs/creatorProfileId 由产物自身声明，`tagRefs`/`creatorProfileId`/homepage 百科主源在 author seal 校验；`5.review` 每对象只留一份 `content_review.json`，AI 只写 `decision/blockingIssues/advisories`，`assetRights`/`dimensions` 由 seal 机械补齐。
- release 只有一个类别 `production`，媒体按公开 slice 交付；对象级权利词汇（`distributionDecision`、`publicationAdmission`、pool `usageScope`）是已冻结在 canonical 字节中的记录事实，保持现有取值。商用级权利字段（modelRelease/propertyRelease/audioRights/commercialAuthorization）只记录不要求。
- approved 对象由 AI 逐个调用单对象事务；release cohort 与 milestone 必须显式，禁止 all-publishable；`objectRefs` 排序、canonical 化与 `expectedCarrierCounts` 派生由 finalize 完成。
- 媒体字节唯一 canonical holder 是仓外 content library（`~/.local/share/quwoquan/content_library`，可用 `QWQ_LIBRARY_ROOT` 覆盖），execution/object-transaction 包/release payload 一律硬链接引用、不产生独立拷贝；publish 事务把已发布对象引用的媒体另拷一份到仓外随体根（默认 `~/.local/share/quwoquan/golden_media`，`QWQ_CARRIED_MEDIA_ROOT` 可指向已备份卷），两处互为备份、都不进 git。任何 gc/hygiene/清理路径不得触碰这两个根；`verify publish-closure` 保证缺失可检测（`DATA.PUBLISH.CARRIED_MEDIA_MISSING` 附 `sourceUrl`）。library 丢失时先运行 `python3 quwoquan_data/scripts/cli.py verify all`，它在跑门禁前会从随体根回填 library。

## Producer 完成与下游 handoff

producer 完成 = 三份 seal receipt 连续闭合 + 逐对象 publish 事务 + `release finalize` 的 immutable handoff。M1/M10/M100/M1000 按 `cumulative_unique_finalized_objects` 计数，每级形成自己的 full explicit cohort/release/handoff；凡已完成 canonical publish 且 review approved 的对象都可复用进入 cohort，handoff 以 canonical publish proof 为凭，不内嵌 execution receipt 链。HANDOFF 只含 release/cohort/milestone/counts/content-pool identity/baseline/contract digest 等 producer facts。

HANDOFF 不含 UAT/sample authority/import/activate/readback、App/API UAT、EAF、environment promotion 或 rollback。任何外部 consumer 结果都不能回写 producer receipt、改变 cohort/release bytes，或成为“内容生产完成”的门槛。

## 工程卫生

`.qwq_output/` 仅放可删除重建的运行产物、证据与缓存；`data/local/` 下只允许 `cache/`、`runs/`、`workspace/`，本次 run 的输入与规划放 `data/local/workspace/<run>/`。控制面真相源不得写入 output。Python bytecode、pytest cache 与工具缓存按仓库既有隔离规则落盘；禁止在仓库根创建临时脚本。不要运行长门禁，按改动范围执行短静态检查或文档引用检查。
