# Creator Pool Pipeline Spec

创作者批量生成管线，与 [`content_pipeline_spec.md`](content_pipeline_spec.md) 同构的 Ralph Loop 证据链。

## 五段对象树

工作区：`${QWQ_DATA_ROOT}/runtime/creator_pools/{vertical}/{batchId}/creators/{creatorRef}/`

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
- commercial 前置：Scale-10 go + seed_handoff + user_pool overlay

### 3. 多样性（Diversity）

Batch-100 商用配额（`diversity_matrix.yaml`）：

| 维度 | 配额 |
|---|---|
| archetype | 8 类：casual_tourist(15)、local_walker(5)，其余 6 类按 plan |
| regionBucket | 7 大区各 ≥8（even split） |
| popularityTier | head 15% / waist 35% / rising 30% / niche 20% |
| outputTier | prolific 40% / steady 45% / seasonal 15% |
| carrierBucket | article 45% / image 30% / mixed 25% |
| topic | ≥12 个 `Topic/旅行/*` 二级主题 |

### 4. 代表性（Representativeness）

原地刷新 `travel_batch_100_v1`（保留 batchId）：

```bash
export QWQ_DATA_ROOT=~/qwq_creator_verify
qwq-data governance creator-pool plan --vertical travel --batch travel_batch_100_v1 --target 100
qwq-data governance creator-pool acquire --batch travel_batch_100_v1
qwq-data governance creator-pool score --batch travel_batch_100_v1
qwq-data governance creator-pool diversify --batch travel_batch_100_v1
qwq-data governance creator-pool enrich --batch travel_batch_100_v1
qwq-data governance creator-pool workflow run --batch travel_batch_100_v1 --through validate
qwq-data verify creator-scale-readiness --mode commercial --target 100 --batch travel_batch_100_v1
```

Acquire 信号：allowlist 域名公开摘要，`derivationPolicy=derivative_persona_v1`，禁止 1:1 复制原名/原图/原 bio。

## hook-check

CLI 返回 0 不等于准出；必须读 `5.validate/review_gate.json`，`passed=false` 时禁止 seed。

## 放量

1. Scale-10：`verify creator-scale-readiness --target 10 --mode trial`
2. Scale-100 trial：需 `artifacts/creator_scale10_readiness.json` decision=go
3. Commercial-100：四支柱全绿 + seed E2E

## CLI

```bash
qwq-data governance creator-pool plan --vertical travel --batch BATCH --target N
qwq-data governance creator-pool diversify --vertical travel --batch BATCH
qwq-data governance creator-pool merge-user-fixtures --vertical travel --batch BATCH
qwq-data governance creator-pool workflow run --vertical travel --batch BATCH --through validate
qwq-data verify creator-scale-readiness --vertical travel --batch BATCH --target N --mode commercial
```
