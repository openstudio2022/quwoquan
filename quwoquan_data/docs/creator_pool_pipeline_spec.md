# Creator Pool Pipeline Spec

创作者批量生成管线，与 [`content_pipeline_spec.md`](content_pipeline_spec.md) 同构的 Ralph Loop 证据链。

## 五段对象树

工作区：`${QWQ_OUTPUT_ROOT}/runtime/creator_pools/{vertical}/{batchId}/creators/{creatorRef}/`

> 目录规范（[`pipeline_directory_layout_spec.md`](pipeline_directory_layout_spec.md) §0.5）：生成过程是仓外一次性 runtime 树；
> 成品经 compact publish 进入仓内 `publish/creators/**`（长期可复用池），后续内容批次通过引用消费，不重新生成、不复制。
> 摘要索引落 `.qwq_output/data/runs/pools/creator/{batchId}/`（index-first 回指），不承载权威证据。

| 阶段 | 必落盘 | 准出门 |
|---|---|---|
| 1.acquire | source_profile.json, sources/01.web_profile/* | acquire_gate.json |
| 2.score | engagement_metrics.json / score.json | score_gate.json |
| 3.enrich | persona_draft.json, enrich_meta.json | enrich_gate.json |
| 4.materialize | creator_bundle.json, manifest.json, _profile.json | materialize_gate.json |
| 5.validate | review.json, provenance.json, persona rubric | **review_gate.json** |

## 批次级 `_shared/`

- creator_pool_plan.json
- diversity_matrix.yaml
- candidate_pool.json（live 模式）
- creator_object_index.json
- creator_workflow_state.json
- batch_manifest.json
- creator_rollup_report.json
- diversity_report.json
- persona_dedup_report.json
- persona_rubric_report.json
- seed_handoff.json
- gate_report.json

## 商用四支柱门禁

### Source Registry

Live acquisition 的唯一来源真相源：

- `verticals/creator_pool/sources/source_registry.yaml`
- 每个站点必须声明 `siteId / verticals / chinaAnalogLabel / candidateRole / crawlAllowed / validationOnly / rightsPolicy / rateLimit / sourceKind`
- `crawlAllowed=false` 的站点只进入 discovery evidence，不进入 raw profile fetch
- 真实平台、博主、奖项、图库只提供公开风格信号、题材分布、地区/器材/载体偏好，不复制真人姓名、头像或 bio
- live candidate pool 禁止 `example.*` 域

### 1. 生产质量（Quality）

| 检查项 | trial | commercial |
|---|---|---|
| reviewGatePassRate | ≥1.0 | ≥1.0 |
| creatorLintPassRate | 抽样 10 | 100/100 |
| provenanceCoverage | ≥1.0 | ≥1.0 + citedSourcePaths 非空 |
| duplicatePersonaP95 | <0.75 | <0.75（bio+headline Jaccard） |
| personaRubricPassRate | ≥0.8 | ≥0.95 |

Persona rubric 最低线见 `schema/creator/creator_persona_rubric.json`：

- bio/headline 非空且达最小长度
- 同 batch 相似度 < 0.85
- disclosure.visible=true，forbiddenClaims 无违规
- displayName/userHandle 非空，≥6 archetype 覆盖

### 2. 平稳性（Stability）

- workflow 幂等：同 batchId 重跑 acquire→validate 不增 failedObjects
- seed 幂等：`merge-user-fixtures` 按 subAccountId upsert
- commercial 前置：canonical `travel_photo_1k_v1`（1200 unique -> travel/photo 双 1000 view）seed_handoff + user_pool overlay；历史 Scale-10 只保留为私有算法 fixture，不进入 service active seed

### 3. 多样性（Diversity）

每 shard 商用配额（`diversity_matrix.yaml`）；`travel_photo_1k_v1` 由 10 个 shard 合计 1200 unique，导出 travel/photo 双 1000 view：

| 维度 | 配额 |
|---|---|
| verticalSegment | travel_primary 20 / photography_primary 20 / travel_photography_cross 80 |
| archetype | travel、photography、travel_photography_cross 三段各自均匀覆盖 |
| regionBucket | 7 大区各 ≥8（even split） |
| sourceRegionClass | non_china 45% / china 35% / cross_region 20% |
| popularityTier | head 15% / waist 35% / rising 30% / niche_expert 20% |
| outputTier | prolific 40% / steady 45% / seasonal 15% |
| carrierBucket | article / image / mixed 均匀覆盖，摄影与交叉类以 image/mixed 为主 |
| platformBucket | 单平台占比 ≤15% |
| topic | ≥12 个 `Topic/旅行/*` 或 `Topic/摄影/*` 主题 |
| cross dual tag | travel_photography_cross 100% 同时具备 `travel`、`photography` verticalRefs 与双类 topic tags |

### 4. 代表性（Representativeness）

当前唯一 active 试跑池为 `travel_photo_1k_v1`：

```bash
unset QWQ_DATA_ROOT
export QWQ_OUTPUT_ROOT="$PWD/.qwq_output"
qwq-data governance creator-pool workflow run --vertical travel --batch travel_photo_1k_v1 --target 120 --through validate
qwq-data governance creator-pool workflow run --vertical travel --batch travel_photo_1k_v1 --target 1200 --through validate
qwq-data governance user-pool rebuild-prefab-users --batch travel_photo_1k_v1 --target-creators 1200
qwq-data verify creator-scale-readiness --mode commercial --target 1200 --batch travel_photo_1k_v1
```

Acquire 信号：从 source registry 生成 `site × verticalSegment × archetype × region × topic × carrier × platform` 候选，`derivationPolicy=derivative_persona_v1`，禁止 1:1 复制原名/原图/原 bio。

## hook-check

CLI 返回 0 不等于准出；必须读 `5.validate/review_gate.json`，`passed=false` 时禁止 seed。

## 放量

1. Per-shard 120 unique：每 shard 固定 20 travel / 20 photography / 80 cross，对应 travel/photo 各 100 view。
2. Canonical 1200 unique：`travel_photo_1k_v1` 十个 shard 聚合，导出双 1000 view、800 overlap。
3. Commercial：四支柱全绿 + seed/content/relation/publish E2E；service active seed 不再保留 batch100/scale10。

## CLI

```bash
qwq-data governance creator-pool plan --vertical travel --batch BATCH --target N
qwq-data governance creator-pool diversify --vertical travel --batch BATCH
qwq-data governance creator-pool merge-user-fixtures --vertical travel --batch BATCH
qwq-data governance creator-pool workflow run --vertical travel --batch BATCH --through validate
qwq-data verify creator-scale-readiness --vertical travel --batch BATCH --target N --mode commercial
```
