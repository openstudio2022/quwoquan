# 六步契约

每步三栏：AI 做什么 / 脚本做什么 / 唯一硬门。物理目录沿用 `1.download/`（acquire）、`4.draft/`（author）、`5.review/`（review），receipt 序号固定 `001-1.download`、`002-4.draft`、`003-5.review`。execution 根：`.qwq_output/data/tasks/<executionId>/`，对象目录：`posts/<carrier>/<angle>/<title>/<seq>/` 或 `entities/<域>/<类型>/<名称>/`。

## 1. init

- AI：一轮写一份 `round.json`，声明本轮各 carrier 的 `executionId` 与逐 target 身份；`familyRef`、`quota`、`status`、`candidateCount`、`entityCatalogDigest` 全部由脚本派生：

```json
{"schema":"quwoquan_data.round_spec",
 "executions":{"homepage":"<id>","article":"<id>","image":"<id>","video":"<id>"},
 "targets":[
  {"carrier":"homepage","entityType":"地点/景区","name":"...","region":"中国/<省>/<市>"},
  {"carrier":"article","entityType":"地点/景区","name":"...","publishAngle":"人文","publishTitle":"..."},
  {"carrier":"image","entityType":"地点/景区","name":"...","publishAngle":"建筑","publishTitle":"..."}]}
```

只声明本轮实际有 target 的 carrier；`region` 必须是现有 `Topic/地理/行政区/<region>` 节点；post 载体 `publishSeq` 缺省 1。`executionId` 格式 `YYYYMMDD--<vertical>-<carrier>-<intent>--<scope>--<pilot|scale|full>-<seq三位>`。补齐 blocked execution 时在 `retryOf` 按 carrier 给出前序 `executionId`。
- 脚本：`python3 quwoquan_data/scripts/cli.py task init --round <round.json>` 逐 carrier 原子写 `execution_manifest.json`、`0.plan/request.json`、`0.plan/target_set.json`，逐 execution 报告 `created|replayed`。
- 硬门：executionId 合法且 create-once；target 身份唯一；homepage 的 `region` 可解析。

## 2. acquire

- AI：出网只在这一步、只由 AI 做——检索条目与文件页、逐字抄下 license/作者/`sha1`/说明、用 `curl -L -A "<固定 UA>" -o <本地路径> <直链>` 下载、亲笔写 page 来源的 `source.md`（首行 H1 为标题，含可见正文与信息区取证）、看图申报水印三字段。随后按 execution 写一份 `ingest.json`：

```json
{"schema":"quwoquan_data.ingest_manifest","executionId":"<id>","targets":[
 {"targetRef":"entities/地点/景区/<名>","sources":[
  {"kind":"page","sourceUrl":"https://zh.wikipedia.org/wiki/...","title":"...","sourceMarkdownPath":"<本地 source.md>",
   "license":"CC BY-SA 4.0","licenseUrl":"https://creativecommons.org/licenses/by-sa/4.0/","creator":"<条目>条目贡献者","relevance":"..."},
  {"kind":"image","sourceUrl":"https://commons.wikimedia.org/wiki/File:...","directUrl":"https://upload.wikimedia.org/...","filePath":"<本地文件>",
   "sha1":"<Commons imageinfo.sha1>","license":"CC BY-SA 4.0","licenseUrl":"https://creativecommons.org/licenses/by-sa/4.0","creator":"...",
   "description":"...","relevance":"...","watermarkStatus":"absent","watermarkKind":"none"}]}]}
```

video 来源另写 `hasAudio`；`watermarkStatus=present` 时 `watermarkKind` 必须是 `author_signature|platform_logo|stock_agency|other` 之一并写 `watermarkNote`。清单里不允许出现 `rightsStatus`、`sha256`、`mime`、尺寸这类脚本能算出来的字段。同一来源站点的请求串行、固定间隔、遇 429 退避；并行子 Agent 不得同时打同一站点。
- 脚本：`python3 quwoquan_data/scripts/cli.py task acquire --execution-id <id> --input <ingest.json>` 零网络：从本地字节算 sha256、按申报 `sha1` 交叉校验、探测 mime/尺寸/时长；图片按载体预算降采样、视频超预算或容器不在 `mp4|webm` 时转码为 H.264 mp4 并抽 poster，降采样/转码/抽帧写进 `derivedModifications`；按申报 license 派生 `rightsStatus`（白名单 CC0/CC BY/CC BY-SA/PD → `verified`，其它可读 → `unverified` 并写 `rightsIssues`，不可读 → `unknown`，任何取值不阻断）；写 `sources/<unit>/{meta.json,source.md,assets/}` 与 `1.download/source_refs.json`，媒体字节入 content library。逐 target 独立报告：全部成功退出 0，部分失败退出 1 并在 `targets[].issue` 给 typed code，清单本身非法退出 2。
- 硬门：申报 `sha1` 与字节一致；权利字段（`sourceUrl/license/licenseUrl/creator`）在场；视频可探测、可播放。
- seal：`task seal --execution-id <id> --stage 1.download --input <seal.json>`，`seal.json` 只含 `actor` 与 `verdict`。

## 3. author

- AI：读 `source.md` 与 `assets/index.json`，每对象只写一个产物：homepage `4.draft/page.md`；article `4.draft/draft.article.md`（frontmatter 写 `title/tagRefs/creatorProfileId`，正文可引用 `assets/` 中的 assetRef）；image `4.draft/image_work.json`；video `4.draft/video_script.json`。正文主张不越出来源；适度润色即可，不要求字数与评分。`4.draft/` 允许放草稿以外的笔记文件。
- 脚本：无。
- 硬门：每对象恰有一个 carrier 产物且非空；`tagRefs` 全部解析到 taxonomy；`creatorProfileId` 缺省或解析到 creator 注册表；homepage 至少一个百科 `page` 来源；同一 execution 全部对象由一个真实 author actor 完成。
- seal：`task seal --stage 4.draft`，`seal.json` 含真实 `actor{host,sessionId,modelFamily,invocation{provider,model,runId}}`。

## 4. review

- reviewer 会话读该 execution 全部产物与来源，写一份 execution 级 `seal.review.json`，`reviews` 以 `targetRef` 为键、逐对象只写判断字段：

```json
{"actor":{...reviewer 真实 actor...},"verdict":"pass",
 "reviews":{
  "posts/article/人文/<title>/1":{"decision":"approved","blockingIssues":[],"advisories":["标题可更具体"]},
  "posts/article/人文/<title2>/1":{"decision":"rejected","blockingIssues":["关键论断无来源支撑"],"advisories":[]}}}
```

只在三类情形 reject：关键论断缺证据、安全/隐私、素材不相关或不可播放。文风/结构/长度/权利疑虑写入 `advisories`。可选 `safety: ok|concern`，可选对个别资产写 `assetRights:[{"assetRef":"assets/...","issues":["..."]}]` 作为记录。

- 脚本：`task seal --stage 5.review --input <seal.review.json>` 把 `reviews` 扇出为逐对象 `5.review/content_review.json`（create-once），从对象实际引用的资产机械补齐 `assetRights`（缺省 `decision=approved`、转录 `sourceUrl/license/termsUrl/authorizationProof/usageScope`）、缺省单维 `dimensions`、`schema/stage/executionId/objectRef/draft{ref,digest}`，校验 schema，并核对 reviewer actor 与 author actor 的 sessionId/runId 不同。`reviews` 必须恰好覆盖 target set；单阶段扇出，不读其它 receipt、不推进。
- 硬门：reviewer ≠ author；每对象一份 review。approved 与 rejected 可并存；零 approved 才 blocked。

## 5. publish

- AI：无需写文件。
- 脚本：`python3 quwoquan_data/scripts/cli.py release publish-object --execution-id <id> --target-ref <ref>` 只对 approved 对象执行一次原子事务：从 `target_set` + `source_refs` + author 产物 + review 投影 canonical 包（`manifest.json/rights.json/asset.refs.json/creator.refs.json/tag.refs.json/source_catalog.json/content_review.json` 与正文/`_entity.json`），写 `quwoquan_data/publish/**` 与 pool record；媒体字节以 content library 硬链接引用，并另拷一份到仓外随体根（`QWQ_CARRIED_MEDIA_ROOT`，默认 `~/.local/share/quwoquan/golden_media`），两处互为备份、都不进 git。
- 硬门：review approved 且 seal 链完整；对象身份唯一 create-once；媒体 bytes 与 library 一致。`rightsStatus/rightsIssues/distributionDecision` 只写入 `rights.json` 与 header 计数，不拒绝对象。

## 6. release

- AI：写显式 cohort（`objectRefs[]`、`milestone`、`producerBaselineRevision`；`releaseClass` 缺省 `production`，`expectedCarrierCounts` 缺省由脚本按 objectRefs 派生）。
- 脚本：`python3 quwoquan_data/scripts/cli.py release finalize --release-id <id> --cohort-file <cohort.json> --milestone <M1|M10|M100|M1000> --producer-baseline-revision <40-hex>` 自行排序 `objectRefs`、canonical 化 cohort，一次完成 pool-build、release-integrity 与 immutable handoff。
- 硬门：cohort 对象全部已 publish；四载体计数不低于里程碑目标；release merkle 与媒体持有闭包；handoff create-once。
