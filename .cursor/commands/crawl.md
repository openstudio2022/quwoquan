---
name: /crawl
id: crawl
category: Workflow
description: quwoquan_data 的 runtime / hybrid 总控
---

## 目标

`/crawl` 是 `quwoquan_data` 的总控命令。当前只允许围绕 `runtime/` 工作，不再把仓库根的 `crawl_specs/trees/runs/publish/out/raw` 当正式运行目录。

运行时真相源：

- spec：`quwoquan_data/runtime/specs/{spec_id}.yaml`
- instruction：`quwoquan_data/runtime/runs/{spec_id}/instruction_profile.json`
- source registry：`quwoquan_data/runtime/seed/source_registry.yaml`
- entity catalog：`quwoquan_data/runtime/seed/entity_catalog/*.ndjson`
- tag catalog：`quwoquan_data/runtime/seed/tag_catalog/*.ndjson`
- graph：`quwoquan_data/runtime/seed/graph/*.ndjson`
- discovery：`quwoquan_data/runtime/runs/{spec_id}/discovery.json`
- topic_task：`quwoquan_data/runtime/runs/{spec_id}/topic_tasks.ndjson`
- entity authority/content 中间态：`quwoquan_data/runtime/runs/{spec_id}/entities/{entity_id}/authority_profile.json|authority_pool.ndjson|content_pool.ndjson`
- topic 中间态：`quwoquan_data/runtime/runs/{spec_id}/topics/{topic_id}/source_pool.ndjson`、`pages/{source_id}/page.html`、`pages/{source_id}/source.md`、`pages/{source_id}/asset_manifest.json`、`enrichment.ndjson`
- 创作 / 审核产物：`quwoquan_data/runtime/runs/{spec_id}/topics/{topic_id}/compose_summary.json`、`audit_summary.json`
- 原生抓取：`quwoquan_data/runtime/downloads/sources/**`、`quwoquan_data/runtime/downloads/images/**`
- 发布真相源：`quwoquan_data/runtime/publish/{topic_id}/posts/{post_id}/article.md|gallery.md|manifest.json|post.json|review.json`

## 三角色主线

```mermaid
flowchart LR
  runtimeSpec[runtime/specs/*.yaml] --> discovery[crawl spec-discovery]
  discovery --> topicTasks[topic_tasks.ndjson]
  topicTasks --> hydrate[crawl fetch-source]
  hydrate --> compose[crawl compose-topic]
  compose --> composeSummary[compose_summary.json]
  composeSummary --> audit[crawl audit-topic]
  audit --> reviewArtifacts[audit_summary.json + review.json]
  reviewArtifacts --> gates[authenticity gate + package gate]
```

角色映射：

1. `instruction / entity / authority`：`crawl instruction-build` + `crawl tag-catalog-build` + `crawl entity-catalog-build` + `crawl entities-by-tag` + `crawl authority-sync`
2. `content discover / hydrate / review`：`crawl content-discover` + `crawl content-hydrate` + `crawl content-review`
3. `compose / audit / publish`：`crawl compose-post` + `crawl review-generated` + `crawl publish-approved`
4. `feedback / graph`：`crawl feedback-extract` + `crawl feedback-verify` + `crawl graph-verify`

## 输入

```text
/crawl auto --specs=real_public_examples_001
```

- `specs`：`quwoquan_data/runtime/specs/{spec_id}.yaml` 的 spec_id 列表

## 模式

### auto

职责：

1. 对每个 spec 执行：

```bash
python3 quwoquan_data/tools/cli.py crawl instruction-build --spec <spec>
python3 quwoquan_data/tools/cli.py crawl entities-by-tag --spec <spec>
python3 quwoquan_data/tools/cli.py crawl authority-sync --spec <spec>
python3 quwoquan_data/tools/cli.py crawl content-discover --spec <spec>
```

2. 若内容候选已具备真实 URL，继续执行：

```bash
python3 quwoquan_data/tools/cli.py crawl content-hydrate --spec <spec>
python3 quwoquan_data/tools/cli.py crawl content-review --spec <spec>
```

3. 读取 `runtime/runs/{spec_id}/instruction_profile.json`、`entity catalog`、`authority/content pool`、`discovery.json` 与 `topic_tasks.ndjson`
4. 把 command 层与 tools 层分开：
   - command 层：topic 初始化、状态汇总、调度
   - tools 层：原生抓取 HTML、抽正文、下载图片、提取元数据
5. 先检查 discovery 基线：
   - article topic 数目标 >= 20
   - image topic 数目标 >= 1
   - 每个 topic 的候选目标 >= 20
6. 对已有真实候选但缺失 `pages/*` 的 topic，可先执行：

```bash
python3 quwoquan_data/tools/cli.py crawl fetch-source --spec <spec> --topic <topic_id> --task-type <article|image> --source-id <source_id> --url <url>
```

7. 对 `publishReady=true` 且真实性 gate 通过的 topic，先执行创作角色：

```bash
python3 quwoquan_data/tools/cli.py crawl compose-post --spec <spec> --topics <topic_id> --targets alpha,gamma
```

8. `content-review` 会把通过审核的内容候选桥接回 topic `source_pool.ndjson`，从而保证：
   - `instruction/entity -> authority -> content -> compose -> audit -> publish` 可以直接闭环
   - 无需手工复制 URL 到 topic 工作区
9. 生成完成后必须再执行审核与发布角色：

```bash
python3 quwoquan_data/tools/cli.py crawl review-generated --spec <spec> --topics <topic_id>
python3 quwoquan_data/tools/cli.py crawl publish-approved --spec <spec> --topics <topic_id>
python3 quwoquan_data/tools/cli.py crawl feedback-extract --spec <spec> --topics <topic_id>
python3 quwoquan_data/tools/cli.py crawl feedback-verify --spec <spec>
```

审核与反馈必须把以下结果落盘：

- topic 级：`runtime/runs/{spec_id}/topics/{topic_id}/audit_summary.json`
- post 级：`runtime/publish/{topic_id}/posts/{post_id}/review.json`
- package manifest：`manifest.json.qualityAudit`
- feedback：`runtime/runs/{spec_id}/feedback/*.ndjson`
- graph：`runtime/seed/graph/*.ndjson`

9. 保证 article / image 两条生产线分开推进：
   - article：真实候选目标 >= 20、真实发布目标 >= 6
   - image：优先官方图库/明确授权图库，其次摄影图库
   - Pinterest 只能 discovery-only
   - 若真实性不足，必须降级 `needs_more_evidence`
10. 每轮完成后执行：

```bash
python3 quwoquan_data/scripts/verify/verify_quwoquan_data_source_authenticity.py
python3 quwoquan_data/scripts/verify/verify_quwoquan_data_post_packages.py
```

### manual

职责：

1. 为每个 `publishReady=true` 且 `authenticityBlocked=false` 的 topic_task 输出 worker 启动块
2. 用户在多个 chat/tab 手工粘贴执行
3. 总控负责汇总 spec 级别的 discovery / publish 状态

建议输出块：

```text
/crawl-topic --spec=quwoquan_data/runtime/specs/real_public_examples_001.yaml --topic=real_west_lake_article_001
```

### status

职责：

读取每个 spec 的：

- `runtime/runs/{spec_id}/discovery.json`
- `runtime/runs/{spec_id}/topic_tasks.ndjson`
- `runtime/publish/{topic_id}/posts.ndjson`
- `python3 quwoquan_data/tools/cli.py crawl status --spec <spec>` 输出

至少汇总：

- article / image topic 数
- `candidateFloorMet` 是否全绿
- article 已发布 topic 数是否 >= 6
- image 已发布 topic 数是否满足 spec
- `authenticityBlockedCount`
- package gate 是否通过

## 输出纪律

总控摘要必须包含：

- `spec_id`
- `articleTopicCount / imageTopicCount`
- `minCandidateSourcesPerTask`
- `articleReadyCount / articlePublishedCount / imagePublishedCount`
- `articlePublishFloorMet / imagePublishFloorMet`
- `articleAuthenticityBlockedCount / imageAuthenticityBlockedCount`
- `articleAuditApprovedCount / imageAuditApprovedCount`
- 每个已执行 topic 的：
  - `topic_id`
  - `taskType`
  - `candidateCount / retainedCandidateCount`
  - `verifiedSourceCount / authenticityBlocked`
  - `highValueCandidateCount / qualityExceptionCount`
  - `approvedAssetCount`
  - `composeStatus / auditStatus / auditOverallScore`
  - `runtime/publish/{topic_id}/posts/{post_id}`
- 真实性 gate 结果
- package gate 结果

## article / image 规则

### article

- 前置门禁：版权清晰、无平台水印、非明显广告、非高重复
- `engagementSum = likes + shares + comments`
- 热度前 10% 直通高价值候选
- 其余按 `qualityScore` 排序保留前 20%
- `qualityScore >= 85` 且合规通过，可突破 30% 上限
- 但真实性 gate 失败时必须整体降级，不能用模板正文或占位 evidence 补齐

### image

- 先过权利与水印门禁，不通过直接 rejected
- 默认保留前 30%
- `imageQualityScore >= 88` 且 `rightsStatus = clear` 可突破比例限制
- Pinterest 只能作为发现入口；未明确权利来源、仍带平台痕迹或存在版权争议的素材，不得进入 publish
- gallery/article 的 front matter 只保留 `title / summary / cover_asset_id / template? / fontPreset?`

## 边界

- 不再把仓库根 `crawl_specs/trees/runs/publish/out/raw/batch_plans` 当正式运行目录
- 当前唯一有效的 publish 真相源是 `quwoquan_data/runtime/publish/`
- 不保留旧的多份 candidate / score / cluster 文件模型
- 不绕过登录、验证码、反爬或访问控制
- 不因为“可自动去水印”就放行版权不清图片
- `manifest.json.assets` 中不得出现 `publishEligibility != approved`
- `manifest.compliance.overallStatus != approved` 时 package 必须失败
- `needs_source_discovery` / `needs_more_evidence` 是正常诚实状态，不得再用 mock 产物凑数
