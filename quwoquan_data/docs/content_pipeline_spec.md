# 内容生产管线规格（Agent 生产 · Human-in-loop · 一键发布到运行库）

本规格描述从「人定义任务」到「内容灌入各环境运行库」的端到端主线。所有命令统一经 `qwq-data` CLI 暴露。

## 0. 单一主线与去版本化

- `publish/` 是**唯一发布主线**，目录为 `publish/{posts,entities,tags,index,sample_bundles}/`，无 `v{N}` 版本目录。
- `publish/publish_meta.json` 记录 `lastPromote` / `lastShip` / `lastReleaseId`，无 `activeVersion`。
- 门禁 `verify_no_legacy_hardcode.py` 禁止 `publish/v{N}`、objectKey `/v{N}/` 段、`chuanxi`/`*_v5` 等区域/任务硬编码回归。

## 1. 入口：人定义生成任务

`qwq-data plan` 把内容指令解析为 `compose_brief`（叙事契约 / imagePlan / imagePolicy / mustIncludeFacts）。
垂类（travel/campus…）数据驱动，无 region/task 专属分支。

## 2. Agent 高质量生产（图文 + 关联实体）

标准三段式：`[CLI compose-brief] → [Agent 创作正文写回草稿] → [CLI review/materialize+gate]`。

- 正文只由会话模型创作（`generator=agent`），脚本不拼正文。
- 草稿可声明 `extractedEntities`（如「洛绒牛场」）；review 据此生成实体 sidecar，无主页者**自动生成关联实体主页** `page.md`，使其可关联查看；发布时仍无主页的 entityRef 被过滤。
- 质量门：三道真实性门（出处/模板指纹/事实可回溯）+ 游记感密度 + 载体一致性 + **图文混合编排门**（figure 跨小节穿插、禁空图块、禁大段无图空档；图多转 gallery 配小字）+ 图片精美门（人脸/水印/近重复/文字占比）。

### post 最小发布契约（manifest.json）

只保留发布/渲染/出处必需字段：`topicId/contentType/entityRefs/tagRefs/conditionContext/sourceUrls/assets/template/carrier/generator/generatorModel/citedSourceRefs/reviewDecision/articleMarkdown*/articleAssetManifest/articleRenderProfile/publish*`。
中间态（`storySpine/sourceQuality/relatedSearchPlan/evidenceBundle/sourcePaths`）落 `produce_trace.json`，不进发布契约。

## 3. Human-in-loop 标注账本（唯一发布态真相源）

`_common/review_ledger.py`。每个 `ReviewItem`（image/fact/article）含：
`agentJudgment(credible|doubtful)`、`agentScore(1-5)`、`humanJudgment(unjudged|credible|doubtful)`、`humanScore`、`humanOverride(publishable|discard)`、`reprocessCount`。

派生 `publishState ∈ {fix, discard, publishable}`（`resolve_publish_state` 统一推导，不持久化为事实）：

1. 人裁定优先：`humanOverride` 直接置态；`humanJudgment=credible` 或 `humanScore>=3` → publishable；`doubtful` → fix。
2. 人未裁定看 agent：`agentJudgment=doubtful` 必须人确认（`requireHumanWhenDoubtful`）→ fix；`credible` 且 `agentScore>=3` → publishable，否则 fix。
3. 低质量可再加工，`reprocessCount` 累计；超 `maxAttempts(3)` 锁定，除非人裁定 publishable。

review 写 `produce/review/ledger/{ref}.json` 与 `entities/{ref}.json`；materialize 随 post 拷入 `posts/.../review/`。

`qwq-data annotate`：`--list` 队列；`--ref/--kind/--target` + `--judgment/--score/--override/--reprocess/--note` 下人判定。

## 4. 发布门（promote / ship）

`_common/publish_filter.py` 据账本与实体主页存在性裁决每个 post：
- 文章须 publishable，否则跳过该 post 并报告（不静默 BLOCK 全量）。
- `discard` 图从 `manifest.assets` / `articleAssetManifest` / 正文 `:::figure` 引用一并剔除并删文件。
- `entityRefs` 中无主页（`entities/{d}/{t}/{name}/page.md` 不存在且 sidecar 未标 hasHomepage）者被过滤。

## 5. 一键发布 + 按环境采样 + 服务侧灌库

`qwq-data ship`：promote（task/release→publish）→ 重建 lookup 索引 → 按环境采样写 sample bundle → 更新 `publish_meta.lastShip` →（可选 `--import`）调用服务侧 importer 灌库。

### 按环境采样（确定性）

`deploy/shared/content_sampling_manifest.yaml` 是唯一采样真相源：prod=全量；gamma/beta/alpha 配 `sampleRatio + postCapPerBucket + entityCapPerBucket + maxPosts/maxEntities`。
采样 `rank = sha1(salt|ref) → [0,1)`，`< sampleRatio` 入选，再按 bucket cap / max 截断；同 env/salt 下稳定可重跑。
产出端云桥契约 `publish/sample_bundles/{env}.json`（`{environment, sampleRatio, posts:[postRef], entities:[entityRef], counts}`）。

### 服务侧 importer（真实灌入运行库）

`quwoquan_service/services/content-service/cmd/import`：
- 只读消费 `publish/posts` + `publish/entities`，按 sample bundle 过滤某环境子集；
- 幂等 upsert：posts→`{posts-db}.posts`（`postRef` 唯一索引），entities→`{entities-db}.entities`（`entityRef` 唯一索引）；`createdAt` 仅插入写、`updatedAt` 每次刷新；
- 加载层 `loader.go` 纯函数、可单测（`loader_test.go`，无需 mongo）；
- 写入层 `UpsertPosts/UpsertEntities/EnsureUnique` 由 `mongo_import_test.go` 对真实 mongo 覆盖（插入/字段/幂等重跑/唯一索引/load→upsert 子集）。

```bash
go run ./services/content-service/cmd/import \
  --publish-root ../quwoquan_data/publish \
  --sample-bundle ../quwoquan_data/publish/sample_bundles/gamma.json \
  --mongo-uri mongodb://localhost:27017 --env gamma

# 真实 mongo 写入路径测试（起一次性 mongod，跑完即销毁）
bash quwoquan_service/scripts/content/run_content_import_mongo_test.sh
```

## 6. 测试与门禁（红绿）

| 关注点 | 测试/门禁 |
|---|---|
| asset_id 可读+唯一 | `tests/test_asset_id_stability.py` |
| 账本状态机 | `tests/test_review_ledger_state_machine.py` |
| manifest 最小化 + 账本/实体 sidecar + 关联实体主页 | `tests/test_hitl_pipeline.py` |
| annotate CLI + 发布门 | `tests/test_annotate_publish_filter.py` |
| 确定性采样 + ship e2e | `tests/test_ship_sampling.py` |
| 图文混合编排门 | `tests/test_mixed_layout_gate.py` |
| 端到端 pilot 全绿 | `tests/test_verify_pilot_gwt.py` |
| 服务侧 importer 加载 | `quwoquan_service/services/content-service/cmd/import/loader_test.go` |
| 服务侧 importer mongo 写入路径 | `quwoquan_service/services/content-service/cmd/import/mongo_import_test.go`（`run_content_import_mongo_test.sh` 起临时 mongod） |
| 去版本化/去区域硬编码 | `scripts/verify_no_legacy_hardcode.py` |
| CLI-first | `scripts/verify/verify_cli_first.py` |
