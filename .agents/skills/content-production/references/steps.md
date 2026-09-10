# 六步契约

每步三栏：AI 做什么 / 脚本做什么 / 唯一硬门。物理目录沿用 `1.download/`（acquire）、`4.draft/`（author）、`5.review/`（review），receipt 序号固定 `001-1.download`、`002-4.draft`、`003-5.review`。execution 根：`.qwq_output/data/tasks/<executionId>/`，对象目录：`posts/<carrier>/<angle>/<title>/<seq>/` 或 `entities/<域>/<类型>/<名称>/`。每轮的手写输入只有 `round.json`、每 carrier 一份 `ingest.json`、每 execution 一份 `seal.review.json`，其余全部由脚本派生。

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

只声明本轮实际有 target 的 carrier；`region` 必须是现有 `Topic/地理/行政区/<region>` 节点（control_plane taxonomy 已含全国省市县，含港澳台）；`entityType` 只取 `Entity/地点/*` 现有叶子（景区、自然景观、古镇、打卡地、露营地、温泉、宗教场所、公园、博物馆、遗址…）；post 载体 `publishSeq` 缺省 1。`executionId` 格式 `YYYYMMDD--<vertical>-<carrier>-<intent>--<scope>--<pilot|scale|full>-<seq三位>`。补齐 blocked execution 时在 `retryOf` 按 carrier 给出前序 `executionId`。
- 脚本：`python3 quwoquan_data/scripts/cli.py task init --round <round.json>` 逐 carrier 原子写 `execution_manifest.json`、`0.plan/request.json`、`0.plan/target_set.json`，逐 execution 报告 `created|replayed`。
- 硬门：executionId 合法且 create-once；target 身份唯一；homepage 的 `region` 可解析。

## 2. acquire

- AI：出网只在这一步、只由 AI 做（主会话或该 execution 的 author）。按 [sourcing.md](sourcing.md) 的 exact 模板：检索候选并做候选级质量筛选；用通用工具把来源正文落盘为 `source.md`（维基取 API 正文 + 信息框 wikitext，头条百科取页内结构化 JSON 展平，游记取 HTML→text），首行 H1 为标题，末尾由 AI 亲笔附「信息区取证」段；逐字抄下 license/作者/`sha1`/说明；用合规 UA 的 `curl`/`yt-dlp` 下载媒体；看图申报水印三字段；可选申报热度信号。随后按 execution 写一份 `ingest.json`（推荐用 `jq` 从已保存的 API 响应生成来源行，避免手抄 40 位 sha1）：

```json
{"schema":"quwoquan_data.ingest_manifest","executionId":"<id>","targets":[
 {"targetRef":"entities/地点/景区/<名>","sources":[
  {"kind":"page","sourceUrl":"https://zh.wikipedia.org/wiki/...","title":"...","sourceMarkdownPath":"<本地 source.md>",
   "license":"CC BY-SA 4.0","licenseUrl":"https://creativecommons.org/licenses/by-sa/4.0/","creator":"<条目>条目贡献者","relevance":"...",
   "discoverySignals":{"ctripHeat":9.2,"ctripReviews":57000,"wikiViews30d":2261}},
  {"kind":"image","sourceUrl":"https://commons.wikimedia.org/wiki/File:...","directUrl":"https://upload.wikimedia.org/...","filePath":"<本地文件>",
   "sha1":"<Commons imageinfo.sha1>","license":"CC BY-SA 4.0","licenseUrl":"https://creativecommons.org/licenses/by-sa/4.0","creator":"...",
   "description":"...","relevance":"...","watermarkStatus":"absent","watermarkKind":"none"}]}]}
```

`sha1` 只在来源声明了它（Commons）时填写，Flickr/YouTube 等来源省略，字节以脚本算的 sha256 自证；video 来源另写 `hasAudio`；`watermarkStatus=present` 时 `watermarkKind` 必须是 `author_signature|platform_logo|stock_agency|other` 之一并写 `watermarkNote`。清单里不允许出现 `rightsStatus`、`sha256`、`mime`、尺寸这类脚本能算出来的字段。`discoverySignals` 只记录不判否，键名自定、值为数字。同一来源站点串行、遵守 Crawl-delay、遇 429/503 退避并放弃同一轮次剩余候选；并行子 Agent 不得同时打同一站点。
- 脚本：`python3 quwoquan_data/scripts/cli.py task acquire --execution-id <id> --input <ingest.json>` 零网络：从本地字节算 sha256、按申报 `sha1` 交叉校验、探测 mime/尺寸/时长；图片按载体预算降采样、视频超预算或容器不在 `mp4|webm` 时转码为 H.264 mp4 并抽 poster，降采样/转码/抽帧写进 `derivedModifications`；按申报 license 派生 `rightsStatus`（白名单 CC0/CC BY/CC BY-SA/PD → `verified`，其它可读 → `unverified` 并写 `rightsIssues`，不可读 → `unknown`，任何取值不阻断）；`www.baike.com` 与 zh.wikipedia 登记为 `sourceClass=encyclopedia`，其它站点为 `web_page`；`discoverySignals` 原样进 `meta.json`；写 `sources/<unit>/{meta.json,source.md,assets/}` 与 `1.download/source_refs.json`，媒体字节入 content library。逐 target 独立报告：全部成功退出 0，部分失败退出 1 并在 `targets[].issue` 给 typed code，清单本身非法退出 2。视频 execution 的 acquire 含转码，放到后台 shell 运行，不阻塞其余步骤。
- 硬门：申报 `sha1`（有则）与字节一致；权利字段（`sourceUrl/license/licenseUrl/creator`）在场；视频可探测、可播放。seal 逐对象校验：ingest 失败或字节漂移的对象以 `DATA.SEAL.ACQUIRE_INVALID` typed issue 退轮，至少一个对象取得来源即 `pass`。
- seal：`task seal --execution-id <id> --stage 1.download --input <seal.json>`，`seal.json` 只含 `actor` 与 `verdict`。

## 3. author

- AI：读 `source.md` 与 `assets/index.json`（派发子 Agent 时用一条 shell 把该 execution 全部来源批量 `cat` 出来，不要逐文件 Read），每对象只写一个产物：homepage `4.draft/page.md`；article `4.draft/draft.article.md`（frontmatter 写 `title/tagRefs/creatorProfileId`，正文可引用 `assets/` 中的 assetRef）；image `4.draft/image_work.json`；video `4.draft/video_script.json`。正文主张不越出来源；游记等第三方文本只取事实与路线，亲笔原创，不搬运表达。适度润色即可，不要求字数与评分。`4.draft/` 允许放草稿以外的笔记文件。派发提示词必须内嵌允许的 tagRefs 闭集、`creatorProfileId`、原件图片路径与「读一个写一个」的节律。
- 脚本：无。
- 硬门：每对象恰有一个 carrier 产物且非空；`tagRefs` 全部解析到 taxonomy；`creatorProfileId` 缺省或解析到 creator 注册表；homepage 至少一个百科 `page` 来源；同一 execution 全部对象由一个真实 author actor 完成。seal **逐对象**校验并一次报出全部违规：违规对象以 `DATA.SEAL.DRAFT_INVALID` typed issue 退出本 execution、不进 resultRefs，至少一个合规产物即 `pass`；零合规必须以 `verdict=blocked` 提交。
- seal：`task seal --stage 4.draft`，`seal.json` 含真实 `actor{host,sessionId,modelFamily,invocation{provider,model,runId}}`。

## 4. review

- reviewer 会话读该 execution 全部产物与来源（批量 `cat`；关键论断回查 `source.md`，image 看原件，video 看 poster），写一份 execution 级 `seal.review.json`，`reviews` 以 `targetRef` 为键、逐对象只写判断字段，并按 [quality.md](quality.md) 给该载体六维 1–5 分（只记录）：

```json
{"actor":{...reviewer 真实 actor...},"verdict":"pass",
 "reviews":{
  "posts/article/人文/<title>/1":{"decision":"approved","blockingIssues":[],"advisories":["标题可更具体"],
    "qualityScores":{"fact_traceability":5,"originality":4,"angle_and_title":4,"practical_density":3,"readability":4,"image_match":4},
    "qualityNotes":"路线段缺交通信息"},
  "posts/article/人文/<title2>/1":{"decision":"rejected","blockingIssues":["关键论断无来源支撑"],"advisories":[]}}}
```

覆盖集合恰为 `002-4.draft` receipt resultRefs 的对象集合——4.draft 退轮的对象不需评、也不得评。只在三类情形 reject：关键论断缺证据、安全/隐私、素材不相关或不可播放。文风/结构/长度/权利疑虑写入 `advisories`；评分不改变 decision。可选 `safety: ok|concern`，可选对个别资产写 `assetRights:[{"assetRef":"assets/...","issues":["..."]}]` 作为记录。

- 脚本：`task seal --stage 5.review --input <seal.review.json>` 把 `reviews` 扇出为逐对象 `5.review/content_review.json`（create-once），从对象实际引用的资产机械补齐 `assetRights`（缺省 `decision=approved`、转录 `sourceUrl/license/termsUrl/authorizationProof/usageScope`）、缺省单维 `dimensions`、`schema/stage/executionId/objectRef/draft{ref,digest}`，原样透传 `qualityScores/qualityNotes`（维度必须属于该载体闭集），校验 schema，并核对 reviewer actor 与 author actor 的 sessionId/runId 不同。单阶段扇出，只读直接前序 receipt、不推进。
- 硬门：reviewer ≠ author；每个合规对象一份 review。approved 与 rejected 可并存；零 approved 才 blocked。

## 5. publish

- AI：无需写文件；用一条 shell 循环对 approved 对象逐个调用，**homepage 先于引用它的 post**。
- 脚本：`python3 quwoquan_data/scripts/cli.py release publish-object --execution-id <id> --target-ref <ref>` 只对 approved 对象执行一次原子事务：从 `target_set` + `source_refs` + author 产物 + review 投影 canonical 包（`manifest.json/rights.json/asset.refs.json/creator.refs.json/tag.refs.json/source_catalog.json/content_review.json` 与正文/`_entity.json`），写 `quwoquan_data/publish/**` 与 pool record；媒体字节以 content library 硬链接引用，并另拷一份到仓外随体根（`QWQ_CARRIED_MEDIA_ROOT`，默认 `~/.local/share/quwoquan/golden_media`），两处互为备份、都不进 git。
- 硬门：review approved 且 seal 链完整；对象身份唯一 create-once；媒体 bytes 与 library 一致。`rightsStatus/rightsIssues/distributionDecision` 只写入 `rights.json` 与 header 计数，不拒绝对象；`qualityScores` 原样进 canonical `content_review.json`。

## 6. release

- AI：写显式 cohort（`objectRefs[]`、`milestone`、`producerBaselineRevision`；不写发布类别，`expectedCarrierCounts` 缺省由脚本按 objectRefs 派生）。cohort 由 `jq` 从 `release pool-query --json` 输出显式构造（见 [handoff.md](handoff.md)）。
- 脚本：`python3 quwoquan_data/scripts/cli.py release finalize --release-id <id> --cohort-file <cohort.json> --milestone <M1|M10|M100|M1000> --producer-baseline-revision <40-hex>` 自行排序 `objectRefs`、canonical 化 cohort，一次完成 pool-build、release-integrity 与 immutable handoff，并把 `cohort.json` 与 `producer_release_handoff.json` create-or-same 复制到 `quwoquan_data/reference/releases/<releaseId>/`（受版本控制的耐久副本；`handoff-verify` 仍只读 `.qwq_output/data/releases/`）。
- 硬门：cohort 对象全部已 publish；四载体计数不低于里程碑目标；release merkle 与媒体持有闭包；handoff create-once；副本与输出根逐字节一致。
