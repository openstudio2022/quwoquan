# 六步契约

每步三栏：AI 做什么 / 脚本做什么 / 唯一硬门。物理目录沿用 `1.download/`（acquire）、`4.draft/`（author）、`5.review/`（review），receipt 序号固定 `001-1.download`、`002-4.draft`、`003-5.review`。execution 根：`.qwq_output/data/tasks/<executionId>/`，对象目录：`posts/<carrier>/<angle>/<title>/<seq>/` 或 `entities/<域>/<类型>/<名称>/`。

## 1. init

- AI：按来源单一类型判定写两份输入——`carrier_demand.json`（executionId、carrier、familyRef、quota）与 `candidate_bindings.json`（逐 target 的 entityType/name，post 载体另给 publishAngle/publishTitle/publishSeq）。
- 脚本：`python3 quwoquan_data/scripts/cli.py task init --carrier-demand <path> --candidate-bindings <path>` 原子写 `execution_manifest.json`、`0.plan/request.json`、`0.plan/target_set.json`。
- 硬门：executionId 合法且 create-once；target 身份唯一。

## 2. acquire

- AI：为每个 target 点名来源 URL 并各写一句相关性理由，写 `acquire.json`：

```json
{"schema":"quwoquan_data.acquire_request","sources":[
 {"kind":"page","url":"https://zh.wikipedia.org/wiki/...","relevance":"..."},
 {"kind":"image","url":"https://commons.wikimedia.org/wiki/File:...","relevance":"..."}]}
```

- 脚本：`python3 quwoquan_data/scripts/cli.py task acquire --execution-id <id> --target-ref <ref> --input <acquire.json>` 抓取正文/媒体 bytes，从 Wikipedia/Commons API 取 license、作者、直链，算 sha256，探测 mime/尺寸/时长，视频抽 poster，写 `sources/<unit>/{meta.json,source.md,snapshot.*,assets/}` 与 `1.download/source_refs.json`，媒体字节入 content library。
- 硬门：`https://` 可达；license 在白名单（CC0/CC BY/CC BY-SA/PD）；bytes 与 sha256 精确。
- seal：`task seal --execution-id <id> --stage 1.download --input <seal.json>`，`seal.json` 只含 `actor` 与 `verdict`。

## 3. author

- AI：读 `source.md` 与 `assets/index.json`，每对象只写一个产物：homepage `4.draft/page.md`；article `4.draft/draft.article.md`（frontmatter 写 `title/tagRefs/creatorProfileId`，正文可引用 `assets/` 中的 assetRef）；image `4.draft/image_work.json`；video `4.draft/video_script.json`。正文主张不越出来源；适度润色即可，不要求字数与评分。
- 脚本：无。
- 硬门：每对象恰有一个 carrier 产物且非空；同一 execution 全部对象由一个真实 author actor 完成。
- seal：`task seal --stage 4.draft`，`seal.json` 含真实 `actor{host,sessionId,modelFamily,invocation{provider,model,runId}}`。

## 4. review

- 唯一 reviewer 会话读产物与来源，每对象写 `5.review/content_review.json`，只写判断字段：

```json
{"decision":"approved|rejected",
 "dimensions":[{"name":"...","decision":"approved|rejected","issues":[]}],
 "blockingIssues":[],
 "assetRights":[{"assetRef":"...","decision":"approved|rejected","issues":[],"usageScope":"research"}],
 "safety":"ok|concern","advisories":[]}
```

只在四类情形 reject：关键论断缺证据、安全/隐私、素材不相关或不可播放、权利不允许研究用途。文风/结构/长度写入 `advisories`。

- 脚本：`task seal --stage 5.review` 补齐 `schema/stage/executionId/objectRef/draft{ref,digest}` 与 `assetRights[].{sourceUrl,license,termsUrl,authorizationProof}`（从 source meta 转录），校验 schema，并核对 reviewer actor 与 author actor 的 sessionId/runId 不同。
- 硬门：reviewer ≠ author；每对象一份 review。approved 与 rejected 可并存；零 approved 才 blocked。

## 5. publish

- AI：无需写文件。
- 脚本：`python3 quwoquan_data/scripts/cli.py release publish-object --execution-id <id> --target-ref <ref>` 只对 approved 对象执行一次原子事务：从 `target_set` + `source_refs` + author 产物 + review 投影 canonical 包（`manifest.json/rights.json/asset.refs.json/creator.refs.json/tag.refs.json/source_catalog.json/content_review.json` 与正文/`_entity.json`），写 `quwoquan_data/publish/**` 与 pool record。
- 硬门：review approved 且 seal 链完整；对象身份唯一 create-once；媒体 bytes 与 library 一致。

## 6. release

- AI：写显式 cohort（`objectRefs[]`、`expectedCarrierCounts`、`milestone`、`releaseClass=research`、`producerBaselineRevision`）。
- 脚本：`python3 quwoquan_data/scripts/cli.py release finalize --release-id <id> --cohort-file <cohort.json> --milestone <M1|M10|M100|M1000> --producer-baseline-revision <40-hex>` 一次完成 pool-build、release-integrity 与 immutable handoff。
- 硬门：cohort 对象全部已 publish；四载体计数等于里程碑目标；release merkle 与媒体持有闭包；handoff create-once。
