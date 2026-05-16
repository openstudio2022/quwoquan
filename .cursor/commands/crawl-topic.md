---
name: /crawl-topic
id: crawl-topic
category: Workflow
description: quwoquan_data 单个 runtime topic worker
---

## 目标

`/crawl-topic` 只处理一个 topic_task。它只围绕 `runtime/` 工作，并默认允许在创作 / 审核前后补执行原生抓取。

- `quwoquan_data/runtime/specs/{spec_id}.yaml`
- `quwoquan_data/runtime/runs/{spec_id}/topic_tasks.ndjson`
- `quwoquan_data/runtime/runs/{spec_id}/topics/{topic_id}/source_pool.ndjson`
- `pages/{source_id}/page.html` / `pages/{source_id}/source.md` / `pages/{source_id}/asset_manifest.json` / `enrichment.ndjson`
- `compose_summary.json` / `audit_summary.json`

输出到：

- `quwoquan_data/runtime/publish/{topic_id}/posts/{post_id}`
- `quwoquan_data/runtime/out/{topic_id}/{alpha|gamma}_projection.json`

## 输入

```text
/crawl-topic --spec=quwoquan_data/runtime/specs/real_public_examples_001.yaml --topic=real_west_lake_article_001
```

## 三角色 Worker 主线

```mermaid
flowchart LR
  topicTask[topic_tasks.ndjson row] --> sourcePool[source_pool.ndjson]
  sourcePool --> hydrate[crawl fetch-source / runtime hydrate]
  hydrate --> scoring[article/image scoring]
  scoring --> enrichment[enrichment.ndjson]
  enrichment --> compose[crawl compose-topic]
  compose --> publishTopic[runtime/publish/{topic_id}/posts/...]
  publishTopic --> review[crawl audit-topic]
  review --> gate[真实性 gate + package gate]
```

## 本轮必做步骤

1. 先执行：

```bash
python3 quwoquan_data/tools/cli.py crawl spec-discovery --spec <spec>
```

2. 在 `runtime/runs/{spec_id}/topic_tasks.ndjson` 中定位 `topic_id`
3. 读取 `topics/{topic_id}/source_pool.ndjson`，确认：
   - `taskType` 明确为 `article` 或 `image`
   - `scoringModel` 与任务类型一致
   - 如果 `candidateCount < 20`，必须诚实保留 `needs_more_evidence`
4. 若 source 有真实 URL 但缺少 `pages/*` 证据，先执行：

```bash
python3 quwoquan_data/tools/cli.py crawl fetch-source --spec <spec> --topic <topic_id> --task-type <article|image> --source-id <source_id> --url <url>
```

5. article 任务要核对：
   - 版权 / 水印 / 广告 / 重复门禁
   - `engagementSum`
   - `qualityScore`
   - `hot_top_10pct`、`quality_top_20pct`、`quality_exception` 三类留存
6. image 任务要核对：
   - `rightsStatus`
   - `watermarkStatus`
   - `imageQualityScore`
   - Pinterest 只保留 discovery-only，不默认进 publish
7. 读取 `pages/{source_id}/page.html`、`pages/{source_id}/source.md`、`pages/{source_id}/asset_manifest.json`、`enrichment.ndjson`
8. 若 `enrichment.ndjson` 仍是默认壳，`compose-topic` 会自动补齐 `selectedCandidateIds`、`sourceUrls`、`coverAssetId`、`figureAssetIds/mediaAssetIds` 与 `publishReady`
9. 执行：

```bash
python3 quwoquan_data/tools/cli.py crawl compose-topic --spec <spec> --topic <topic_id> --targets alpha,gamma --dry-run
```

10. 再执行审核角色：

```bash
python3 quwoquan_data/tools/cli.py crawl audit-topic --spec <spec> --topic <topic_id>
```

11. 执行真实性 gate 与 package gate：

```bash
python3 quwoquan_data/scripts/verify/verify_quwoquan_data_source_authenticity.py
python3 quwoquan_data/scripts/verify/verify_quwoquan_data_post_packages.py
```

## 每轮产物

必须至少能追溯到：

- `runtime/runs/{spec_id}/topic_tasks.ndjson`
- `runtime/runs/{spec_id}/topics/{topic_id}/source_pool.ndjson`
- `runtime/runs/{spec_id}/topics/{topic_id}/pages/{source_id}/page.html`
- `runtime/runs/{spec_id}/topics/{topic_id}/pages/{source_id}/source.md`
- `runtime/runs/{spec_id}/topics/{topic_id}/pages/{source_id}/asset_manifest.json`
- `runtime/runs/{spec_id}/topics/{topic_id}/enrichment.ndjson`
- `runtime/runs/{spec_id}/topics/{topic_id}/compose_summary.json`
- `runtime/runs/{spec_id}/topics/{topic_id}/audit_summary.json`
- `runtime/downloads/sources/{spec_id}/{topic_id}/{source_id}/page.html`
- `runtime/downloads/images/{spec_id}/{topic_id}/{source_id}/*`
- `runtime/publish/{topic_id}/posts/{post_id}/article.md|gallery.md`
- `runtime/publish/{topic_id}/posts/{post_id}/manifest.json`
- `runtime/publish/{topic_id}/posts/{post_id}/post.json`
- `runtime/publish/{topic_id}/posts/{post_id}/review.json`

## 输出口径

worker 摘要必须包含：

- `spec_id`
- `topic_id`
- `taskType`
- `candidateCount / retainedCandidateCount`
- `verifiedSourceCount / authenticityBlocked`
- `highValueCandidateCount / qualityExceptionCount`
- `approvedAssetCount`
- `manifest.compliance.overallStatus`
- `review.overallStatus / review.overallScore`
- 生成的 `runtime/publish/{topic_id}/posts/{post_id}` 路径
- 真实性 gate 是否通过
- package gate 是否通过

## 边界

- 不再恢复 `batch/raw/retrieval_plan` 流程
- 当前唯一有效的 publish 真相源是 `quwoquan_data/runtime/publish/`
- 不把 Pinterest 默认当作可直接发布来源
- 不把带平台水印或版权不清图片写入 `images/*`
- 不把 `publishEligibility != approved` 的资产写入最终 manifest
- 不在 front matter 重复写 `entity_refs / source_urls`
- 不把第三方原文整段复制进 `article.md`
- 不因为数量基线压力，把无真实证据 topic 强行发布
