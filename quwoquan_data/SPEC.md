# quwoquan_data 执行规格（runtime / hybrid）

## 1. 目标

`quwoquan_data` 要被当成**真实可用的数据生产系统**，而不是样例数据仓库。

当前唯一主线：

```text
runtime/specs -> discovery -> topic_task -> fetch/hydrate -> publish package -> out
```

核心原则：

- 代码与运行数据分离
- 真实性优先于数量
- article / image 双生产线分开评分与发布
- 任何真实性不足的 topic 一律降级为 `needs_more_evidence`

## 2. 仓库与 runtime 分工

### 2.1 仓库内保留

仓库根 `quwoquan_data/` 只保留：

- `schema/`
- `tools/`
- `tests/`
- `README.md`
- `SPEC.md`
- 必要 `.gitignore`

### 2.2 运行时根

所有真实运行数据统一写入：

- `quwoquan_data/runtime/`
- 或通过环境变量 `QWQ_RUNTIME_ROOT` 指向的 runtime 根

正式结构：

```text
runtime/
├── specs/
├── trees/
├── runs/
├── publish/
├── out/
└── downloads/
```

其中：

- `runtime/specs/{spec_id}.yaml`：运行时 spec 真相源
- `runtime/trees/**`：运行时树真相源
- `runtime/runs/{spec_id}/discovery.json`
- `runtime/runs/{spec_id}/topic_tasks.ndjson`
- `runtime/runs/{spec_id}/topics/{topic_id}/...`
- `runtime/publish/{topic_id}/posts/{post_id}/...`
- `runtime/out/{topic_id}/{alpha|gamma}_projection.json`
- `runtime/downloads/sources/**`：HTML 原始抓取
- `runtime/downloads/images/**`：图片原始下载

### 2.3 测试样例

测试样例只允许进入：

- `quwoquan_data/tests/fixtures/`

仓库根的旧目录：

- `crawl_specs/`
- `trees/`
- `runs/`
- `publish/`
- `out/`
- `raw/`
- `batch_plans/`

都不再作为正式运行真相源使用。当前唯一有效的 publish 真相源是 `runtime/publish/`。

## 3. hybrid 主线

### 3.1 命令编排层

职责：

- 从 spec 生成 topic_task
- 调度单 topic 执行
- 汇总状态
- 更新 discovery / topic task 摘要

当前入口：

- `crawl spec-discovery`
- `crawl status`
- `crawl run-topic`

### 3.2 tools 原生能力

职责：

- HTML 拉取
- 标题/正文段落抽取
- 图片 URL 抽取
- 图片二进制下载
- 基础元数据提取（sha256 / mime / 宽高）
- 质量评分
- 真实性 gate
- package gate

当前入口：

- `crawl fetch-source`
- `tools/native_fetch.py`

## 4. topic 工作区

每个 topic 工作区必须收敛为：

- `runtime/runs/{spec_id}/topics/{topic_id}/source_pool.ndjson`
- `runtime/runs/{spec_id}/topics/{topic_id}/pages/{source_id}/page.html`
- `runtime/runs/{spec_id}/topics/{topic_id}/pages/{source_id}/source.md`
- `runtime/runs/{spec_id}/topics/{topic_id}/pages/{source_id}/asset_manifest.json`
- `runtime/runs/{spec_id}/topics/{topic_id}/enrichment.ndjson`

补抓取规则：

- 若 `source_pool` 已有真实 URL 但 `pages/*` 缺失，`run-topic` 会尝试原生补抓
- 原始 HTML 存入 `runtime/downloads/sources/...`
- 下载到的图片存入 `runtime/downloads/images/...`
- 抽取后的标准化证据回写到 `runtime/runs/.../pages/...`

若 URL 本身明显占位，或抓取失败且没有已有真实证据，则保持 `needs_more_evidence`

## 5. article / image 双任务链

### 5.1 article

article 候选必须显式记录：

- `likes / shares / comments`
- `engagementSum`
- `qualityBreakdown`
- `qualityScore`
- `rightsStatus / watermarkStatus / duplicateStatus / adSignal`
- `selectionDecision / selectionBucket / selectionReason`

article 规则：

- 前置门禁：版权清晰、无平台水印、非明显广告、非高重复
- 热度前 10% 直通高价值候选
- 其余按 `qualityScore` 排序保留前 20%
- 默认保留不超过 30%
- `qualityScore >= 85` 且合规通过可突破 30%

### 5.2 image

image 候选必须显式记录：

- `imageQualityBreakdown`
- `imageQualityScore`
- `rightsStatus / watermarkStatus / sourceRole`
- `selectionDecision / selectionBucket / selectionReason`

image 规则：

- 先过权利与水印门禁，不通过直接 rejected
- 默认保留前 30%
- `imageQualityScore >= 88` 且 `rightsStatus = clear` 可突破比例限制
- Pinterest 只能作为 discovery-only，不默认直接发布

## 6. 真实性 gate

至少拦截：

- 占位 URL
- `公开样本 01` / `图片候选 01` 类标题
- 过短 `source.md`
- 空壳 `page.html`
- `article.md` 模板腔

运行语义：

- 若 topic 缺真实抓取结果，状态只能是 `needs_source_discovery` 或 `needs_more_evidence`
- 不允许为了凑够 `>=20` 或 `>=6` 用合成数据补齐
- `article.md` 必须能映射回 `source.md` 的真实段落

## 7. package gate

`manifest.json` 必须包含：

- `schemaVersion`
- `specId / topicId / postId`
- `contentType`
- `contentMetadata`
- `entityRefs / tagRefs / sourceUrls / selectedSourceIds`
- `compliance.overallStatus`
- `assets[]`

硬门禁：

- `manifest.compliance.overallStatus != approved` -> fail
- `publishEligibility != approved` -> fail
- `rightsStatus != clear` -> fail
- `watermarkStatus != clean` -> fail
- image `mediaUrls / coverUrl` 必须来自 `manifest.assets[].objectKey`
- article payload 禁止 `articleDocument`

## 8. Markdown 与端侧消费

article / gallery front matter 只保留：

- `title`
- `summary`
- `cover_asset_id`
- `template`（article 可选）
- `fontPreset`（article 可选）

实体、标签、来源 URL 真相统一进入 `manifest.json`。

正文仍需保留：

- `## 实体锚点`

## 9. CLI

```bash
python3 quwoquan_data/tools/cli.py tree validate --tree all
python3 quwoquan_data/tools/cli.py crawl spec-discovery --spec quwoquan_data/runtime/specs/real_public_examples_001.yaml
python3 quwoquan_data/tools/cli.py crawl fetch-source --spec quwoquan_data/runtime/specs/real_public_examples_001.yaml --topic real_west_lake_article_001 --task-type article --source-id real_west_lake_article_source_001 --url "https://zh.wikivoyage.org/wiki/%E6%9D%AD%E5%B7%9E"
python3 quwoquan_data/tools/cli.py crawl fetch-source --spec quwoquan_data/runtime/specs/real_public_examples_001.yaml --topic real_west_lake_image_001 --task-type image --source-id real_west_lake_image_source_001 --url "https://commons.wikimedia.org/wiki/File:West_Lake_-_Hangzhou,_China.jpg"
python3 quwoquan_data/tools/cli.py crawl run-topic --spec quwoquan_data/runtime/specs/real_public_examples_001.yaml --topic real_west_lake_article_001 --targets alpha,gamma --dry-run
python3 quwoquan_data/tools/cli.py crawl run-topic --spec quwoquan_data/runtime/specs/real_public_examples_001.yaml --topic real_west_lake_image_001 --targets alpha,gamma --dry-run
python3 quwoquan_data/tools/cli.py crawl status --spec quwoquan_data/runtime/specs/real_public_examples_001.yaml
```

## 10. 验收口径

- runtime 根为默认读写根
- 仓库验证可在无预置 runtime 数据下，通过 `tests/fixtures/runtime_seed/` 起临时 runtime
- `spec-discovery` 可初始化 topic 壳目录，不再依赖根目录旧 runs
- `fetch-source` 可把真实 URL 拉进 runtime
- `run-topic` 可在已有真实证据上自动补全默认 enrichment，并发布 package
- 真实性 gate 与 package gate 都能独立运行

## 11. 当前真实可重跑样例

当前本地 runtime 已保留一套真实可验证样例：

- spec：`quwoquan_data/runtime/specs/real_public_examples_001.yaml`
- article topic：`real_west_lake_article_001`
- image topic：`real_west_lake_image_001`

重跑命令：

```bash
python3 quwoquan_data/tools/cli.py crawl spec-discovery --spec quwoquan_data/runtime/specs/real_public_examples_001.yaml
python3 quwoquan_data/tools/cli.py crawl fetch-source --spec quwoquan_data/runtime/specs/real_public_examples_001.yaml --topic real_west_lake_article_001 --task-type article --source-id real_west_lake_article_source_001 --url "https://zh.wikivoyage.org/wiki/%E6%9D%AD%E5%B7%9E" --title "第一次逛杭州，先把西湖这条线走顺" --query "杭州 西湖 旅行指南 步行" --snippet "中文 Wikivoyage 杭州词条把西湖、湖滨和城市步行节奏写成了旅行指南，更适合重组为用户可读长文。" --rights-status clear --watermark-status clean
python3 quwoquan_data/tools/cli.py crawl fetch-source --spec quwoquan_data/runtime/specs/real_public_examples_001.yaml --topic real_west_lake_image_001 --task-type image --source-id real_west_lake_image_source_001 --url "https://commons.wikimedia.org/wiki/File:West_Lake_-_Hangzhou,_China.jpg" --title "雷峰塔视角下的西湖开阔湖面" --query "West Lake Hangzhou Commons image" --snippet "真实来源基于 Wikimedia Commons 文件页，来源页明确写出作者、拍摄时间和 CC BY-SA 3.0 授权。" --rights-status clear --watermark-status clean
python3 quwoquan_data/tools/cli.py crawl run-topic --spec quwoquan_data/runtime/specs/real_public_examples_001.yaml --topic real_west_lake_article_001 --targets alpha,gamma --dry-run
python3 quwoquan_data/tools/cli.py crawl run-topic --spec quwoquan_data/runtime/specs/real_public_examples_001.yaml --topic real_west_lake_image_001 --targets alpha,gamma --dry-run
```

样例产物路径：

- `runtime/runs/real_public_examples_001/topics/real_west_lake_article_001/pages/real_west_lake_article_source_001/`
- `runtime/publish/real_west_lake_article_001/posts/real_west_lake_article_001_article_001/`
- `runtime/runs/real_public_examples_001/topics/real_west_lake_image_001/pages/real_west_lake_image_source_001/`
- `runtime/publish/real_west_lake_image_001/posts/real_west_lake_image_001_image_001/`
