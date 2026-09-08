# quwoquan_data

`quwoquan_data` 负责 Travel Research 可复用内容输入、不可变 execution 工作包、canonical 内容对象与 immutable producer release handoff。内容生产的唯一流程真相源见 [content-production Skill](../.agents/skills/content-production/SKILL.md)；本 README 只给出工程边界和最短操作入口，不复制步骤细则。

## Skill + AI Agent

宿主 Cursor/Codex IDE/CLI Agent 是唯一内容语义主体：判定来源类型与载体、点名来源 URL 与相关性理由、创作每对象唯一 carrier 产物、以另一个真实会话独立写 `content_review.json` 的判断字段，并显式决定 approved 对象、release cohort 与 milestone。仓库代码只处理 identity-only 初始化、机械取得字节与权利硬事实、schema/digest/ref/media 校验、create-once seal receipt、单对象 publish 与 explicit cohort immutable release。

producer 固定为六步 `init → acquire → author → review → publish → release`，`release finalize` 成功即 `END`。import/activate/readback/health、API/App UAT、EAF、sampling authority、promotion、rollback/replay 全部 out of scope；下游 owner 是 Environment Ops scheduler，Data 不创建环境 acceptance。

actor 契约：主会话拥有澄清、全部机械命令（init/acquire/seal/publish/finalize）、子 Agent 派发、每轮提交与镜像、收官；acquire 的出网取证可由主会话或该 execution 的 author 完成；一个 execution 恰有一个 author actor（主会话或独立子 Agent 会话）拥有 `4.draft`；`review` 由另一个真实 reviewer 会话完成，与该 execution 的 author 不同 session/runId，同一 execution 至多一个 reviewer，不同 execution 可并行。不得新增 resolver/projector/runner/controller/queue/registry/SDK、actor projection、stage-open 或自动恢复。

## 工作包与只读恢复

```text
.qwq_output/data/tasks/<executionId>/
  execution_manifest.json
  0.plan/{request.json,target_set.json}
  sources/<unit>/{meta.json,source.md,snapshot.*,assets/}
  sources/plans/<sha256>.json            # acquire 请求原文
  entities/**/<1.download|4.draft|5.review>/
  posts/<carrier>/**/<1.download|4.draft|5.review>/
  _shared/receipts/{001-1.download,002-4.draft,003-5.review}.json
  evidence/object-transactions/
```

恢复只读 `_shared/receipts/`：找首个未闭合步骤继续；最后一份 receipt 为 `blocked` 时创建新 execution。恢复不改写旧 receipt，也不从聊天摘要、宿主调度或环境状态推断 producer 进度。

```bash
python3 quwoquan_data/scripts/cli.py task init --help
python3 quwoquan_data/scripts/cli.py task acquire --help
python3 quwoquan_data/scripts/cli.py task seal --help
```

## 取得、发布与 release

`task acquire` 是零网络 ingest：出网检索、取证与下载全部由 AI 用通用工具按 Skill 的来源矩阵与合规闭集完成（zh.wikipedia / 头条百科 / Commons / 携程游记 / Flickr CC / YouTube CC 等），AI 按 execution 提交一份 ingest 清单（本地文件路径 + 申报的 `sourceUrl/directUrl/license/licenseUrl/creator/sha1/description/relevance`、水印三字段、可选 `discoverySignals`；page 来源附落盘并附取证段的 `source.md`）；脚本只从本地字节算 sha256、按申报 sha1 交叉校验、探测 mime/尺寸/时长、图片按预算降采样、视频超预算或容器不在 `mp4|webm` 时转码为 H.264 mp4 派生体并抽 poster。license 只记录并派生 `rightsStatus`（白名单 CC0/CC BY/CC BY-SA/PD → verified，其它 → unverified/unknown），不阻断。

`4.draft` 每对象只保留 `page.md|draft.article.md|image_work.json|video_script.json` 之一，标题/tagRefs/creatorProfileId 由产物自身声明，seal 逐对象校验、违规对象以 typed issue 退轮；`5.review` 每对象只保留 `content_review.json`，AI 只写 `decision/blockingIssues/advisories` 与只记录的 `qualityScores/qualityNotes`，`task seal --stage 5.review` 按 `002-4.draft` resultRefs 覆盖并补齐 `assetRights`、`dimensions` 与机械字段。approved 对象逐个 `publish-object`；`release finalize` 消费 AI 显式 cohort（`releaseClass` 唯一取值 `production`，计数不低于里程碑目标即达标），一次完成 pool-build、release-integrity 与 create-once handoff，并把 `cohort.json`/`producer_release_handoff.json` 复制到受版本控制的 `reference/releases/<releaseId>/`。

## 持久性

- `quwoquan_data/publish/**` 是 canonical 对象元数据（JSON/MD），受版本控制，与代码同等重要。
- 媒体字节的运行时 holder 是仓外 content library（默认 `~/.local/share/quwoquan/content_library`，`QWQ_LIBRARY_ROOT` 可覆盖）；execution、object-transaction 包与 release payload 只以硬链接引用它。
- 随体媒体根（默认 `~/.local/share/quwoquan/golden_media`，`QWQ_CARRIED_MEDIA_ROOT` 可指向已备份卷）是已发布对象所引用媒体的仓外 durable 副本，由 publish 事务写入，与 content library 互为备份；两处都不进 git，也都在 `git clean` 射程之外。任何 gc/hygiene/清理路径不得触碰这两个根。library 丢失时运行 `python3 quwoquan_data/scripts/cli.py verify all`，它在跑门禁前会从随体根逐 sha 校验并回填 library；`verify publish-closure` 对 canonical 引用的每个媒体摘要检查两处至少一处可达，缺失即 `DATA.PUBLISH.CARRIED_MEDIA_MISSING` 并附 `sourceUrl`，字节可按来源直链原样重取。
- `quwoquan_data/reference/releases/<releaseId>/{cohort.json,producer_release_handoff.json}` 是里程碑 release 的版本化副本，由 `release finalize` create-or-same 写入；它只是耐久备份，`handoff-verify` 仍只读 `.qwq_output/data/releases/`。
- 每轮收官后 `publish/**` 随 `content(data)` 提交入库，随体根 rsync 到用户指定备份路径；`.qwq_output/` 全部可删除重建，删除后 release 媒体可从 library/随体根重建、release 目录可由版本化 cohort 重新 finalize。

```bash
python3 quwoquan_data/scripts/cli.py release publish-object --help
python3 quwoquan_data/scripts/cli.py release finalize --help
python3 quwoquan_data/scripts/cli.py release handoff-verify --help
```

M1/M10/M100/M1000 按 `cumulative_unique_finalized_objects` 累计，每级形成自己的 full explicit cohort/release/handoff；凡已完成 canonical publish 且 review approved 的对象都可复用进入 cohort。handoff 以 canonical publish proof 为凭，记录 `producerBaselineRevision` 与 `producerContractDigest`，不含 UAT/import/readback/EAF/promotion/rollback。任何外部 consumer 只可只读上述 immutable producer facts。

## 可复用输入与输出边界

受版本控制的可复用输入只位于 `control_plane/`、`verticals/`、`reference/`、`prompts/`、`templates/` 与 `schema/`；不得写入任务地区、数量、日期、execution identity 或运行输出。唯一例外是 `reference/releases/<releaseId>/` 里由 finalize 写入的里程碑 cohort/handoff 版本化副本——它们是 terminal 事实的耐久备份而不是可复用输入。`publish/` 只保存 approved canonical objects 及其必要引用闭包，不保存 raw source、草稿、prompt、日志或 receipt。

`.qwq_output/data/` 一级只允许：

```text
tasks/       不可变 producer execution 工作包与 create-once receipts
releases/    环境无关 immutable release 与 handoff 事实
local/       cache/ runs/ workspace/ 三个子目录；本次 run 的输入放 workspace/<run>/
```

删除 `.qwq_output/` 不得损失依赖声明、recipe、prompt、template、schema、policy 或部署规则。静态检查的组合入口保持为：

```bash
python3 quwoquan_data/scripts/cli.py verify all
```
