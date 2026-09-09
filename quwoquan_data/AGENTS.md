# quwoquan_data Agent Guide

在 `quwoquan_data/` 工作时，除仓库根 `AGENTS.md` 外先阅读 `quwoquan_data/README.md`。

## Data 内容生产边界

`.agents/skills/content-production/SKILL.md` 是 Data producer 六步（init → acquire → author → review → publish → release）的唯一流程真相源；本文件只约束工程边界，不复制步骤正文。producer 从主题到 `release finalize` 的 immutable handoff 即结束。import/activate/readback/health、API/App UAT、EAF、sampling authority、promotion、rollback 与 replay 全部 out of scope，不进入 handoff、恢复或完成条件；下游 owner 是 Environment Ops scheduler（EAF v2 profile 闭集 `smoke|integration|release`），Data 不写 EAF。

宿主 Cursor/Codex Agent 是唯一语义主体，以原生通用工具按 Skill 来源矩阵取证下载、看图、创作和独立评审，并显式决定 approved 对象、cohort 与 milestone；来源、质量评分及水印申报细则只读 Skill references。职责边界只按可伪造性划分：同样字节换任何执行者结果相同且不可伪造的归代码；需要理解语义或看见内容的归 AI。代码不得出网、不得决定来源、相关性、内容、review、verdict、评分、typed issue、approved、cohort、milestone、后继或恢复。`quwoquan_data/scripts/content/source/**`、`content/execution/**` 与 `core/**` 不得存在任何 HTTP/socket 出网点（由 local_contract 静态门锁定）；环境回读的 `content/release/environment/public_api_client.py` 验证的是自家服务而非来源站点，不在此限。

代码边界仅为六条单阶段、无状态、无恢复命令：`task init`、`task acquire`、`task seal`、`release publish-object`、`release finalize`、`release handoff-verify`。各命令输入、字节派生、逐对象拒绝、seal 覆盖与版本化副本规则只读 [六步契约](../.agents/skills/content-production/references/steps.md) 和 [handoff 契约](../.agents/skills/content-production/references/handoff.md)，不在本文件复制流程。`handoff-verify` 只读输出根；命令不得跨阶段推进或恢复。

actor 契约：主会话拥有与用户澄清、全部机械命令、子 Agent 派发、每轮提交与镜像、收官；acquire 的出网取证与 ingest 清单可由主会话或该 execution 的 author 完成；一个 execution 恰有一个 author actor（可为主会话或宿主派发的独立子 Agent 会话）拥有 `4.draft`；`5.review` 由另一个真实 reviewer 会话完成，与本 execution author 不同 session/runId，同一 execution 同时至多一个 reviewer 调用，不同 execution 可并行。禁止 stage-open、宿主 verifierFacts、resolver/projector/runner/controller/queue/registry/SDK、actor projection、stage-gate、自动恢复、execution-state reducer 或轮次台账。凡跨阶段推进、读 receipt 决定下一步、重试或恢复都属被禁的 runner。任何旧轨引用、import、CLI、schema、fixture、test 与文档在物理删除增量中归零，不得用 shim 或 dual-read 保留。

新能力优先进入 `python3 quwoquan_data/scripts/cli.py <command>` 的现有边界，不新增可直接运行的业务脚本，也不在 `.qwq_output/` 留不可从版本控制真相源重建的助手脚本。authoring source 先行。脚本不得拼正文、image caption、video script、`content_review.json` 的判断字段、typed issue 或 verdict。

## 内容与证据

- 实体口径与配比：实体是用户愿意去的一切地方（景区、秘境、网红打卡地、古镇、露营地、温泉…），类型只取 `Entity/地点/*` 现有叶子；一个实体默认产 1 homepage + 1 article（换角度）+ 1–2 image [+ video]。homepage 主源必须是百科闭集（zh.wikipedia / 头条百科）；article 以实体条目换角度或主题条目为主源，携程游记等只作 `factual_reference_only` 事实参考；image/video 的主源是文件页/作品页。来源矩阵 v2 与 `accessPolicy` 闭集见 Skill `references/sourcing.md`：robots/ToS 限制只记录为 `accessPolicy`（`open|robots_disallowed|tos_restricted`）不阻断入池，版权保留/权利未知来源按 `unverified`/`unknown` + `authorizationRequired` 入池，开发验证默认公开；只有技术性规避（登录墙/付费墙/验证码/DRM/反爬挑战）仍禁止。
- 硬门只有五条：来源 `sourceUrl/directUrl` 为 `https://` 且申报 sha1（有则）与本地字节一致；bytes 与 sha256 精确；权利字段（`sourceUrl/license/licenseUrl/creator`）在场（license 只记录并派生 `rightsStatus`：白名单 CC0/CC BY/CC BY-SA/PD → verified，其它可读 → unverified 并写 `rightsIssues`，不可读 → unknown；任何取值不阻断）；author 与 reviewer 是不同 session/runId；对象身份唯一且 create-once；显式 cohort 且四载体计数不低于里程碑目标。水印（`watermarkStatus/watermarkKind/watermarkNote` 由看过像素的 AI 申报，缺席只能记 unknown，`present` 汇总进 release header `watermarkedAssetIds`）、文风、结构、长度、配图率、质量评分（`qualityScores` 四载体各六维 1–5，只记录）、热度信号（`discoverySignals`）、权利疑虑等只作记录或 advisory。文章配图张数不设下限。
- 放弃而不阻塞：候选级失败（含热点/质量筛选不合格、站点需技术性规避、429/503）换候选；对象级失败（含 4.draft 产物违规）该对象退轮、execution 继续、receipt 仍 `pass`；execution 级身份/完整性失败该 execution `blocked`，以 `retryOf` 新建补齐；四载体计数不达标是账不是失败。每轮收官六段报告（目标 vs `pool-query` 计数、新增/复用、放弃清单、blocked 与首个 typed blocker、缺口、下一轮入口）附评分分布，计数只从 `pool-query` 读；每轮收官后按 `commit` Skill 提交 `publish/**` 并 rsync 随体根到备份路径。
- `4.draft` 每对象只留一个 carrier 主产物（`page.md|draft.article.md|image_work.json|video_script.json`），标题/tagRefs/creatorProfileId 由产物自身声明，`tagRefs`/`creatorProfileId`/homepage 百科主源在 author seal 校验；`5.review` 每对象只留一份 `content_review.json`，AI 只写 `decision/blockingIssues/advisories`，`assetRights`/`dimensions` 由 seal 机械补齐。
- release 默认单链路，不携带发布类别或命名就绪轨道，环境差异只由显式环境配置表达，媒体按公开 slice 交付；对象级权利词汇（`distributionDecision`、`publicationAdmission`、pool `usageScope`）是已冻结在 canonical 字节中的记录事实，保持现有取值。商用级权利字段（modelRelease/propertyRelease/audioRights/commercialAuthorization）只记录不要求。
- approved 对象由 AI 逐个调用单对象事务；release cohort 与 milestone 必须显式，禁止 all-publishable；`objectRefs` 排序、canonical 化与 `expectedCarrierCounts` 派生由 finalize 完成。
- 媒体字节唯一 canonical holder 是仓外 content library（`~/.local/share/quwoquan/content_library`，可用 `QWQ_LIBRARY_ROOT` 覆盖），execution/object-transaction 包/release payload 一律硬链接引用、不产生独立拷贝；publish 事务把已发布对象引用的媒体另拷一份到仓外随体根（默认 `~/.local/share/quwoquan/golden_media`，`QWQ_CARRIED_MEDIA_ROOT` 可指向已备份卷），两处互为备份、都不进 git。任何 gc/hygiene/清理路径不得触碰这两个根；`verify publish-closure` 保证缺失可检测（`DATA.PUBLISH.CARRIED_MEDIA_MISSING` 附 `sourceUrl`）。library 丢失时先运行 `python3 quwoquan_data/scripts/cli.py verify all`，它在跑门禁前会从随体根回填 library。

## Producer 完成与下游 handoff

producer 完成判据、里程碑累计计数、对象复用与 handoff 字段只读 [Skill 完成证据](../.agents/skills/content-production/SKILL.md#完成证据) 及 [handoff 契约](../.agents/skills/content-production/references/handoff.md)。任何下游 consumer 结果都不能回写 producer receipt、改变 cohort/release bytes 或成为 producer 完成门槛。

## 工程卫生

`.qwq_output/` 仅放可删除重建的运行产物、证据与缓存；`data/local/` 下只允许 `cache/`、`runs/`、`workspace/`，本次 run 的输入与规划放 `data/local/workspace/<run>/`。控制面真相源不得写入 output。Python bytecode、pytest cache 与工具缓存按仓库既有隔离规则落盘；禁止在仓库根创建临时脚本。不要运行长门禁，按改动范围执行短静态检查或文档引用检查。
