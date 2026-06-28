# system-creator-pool

## 概述

批量旅行垂类 AI 创作者生成管线：从公开作者信号衍生 persona，经五段对象树物化为可 seed 的 CreatorBundle，支撑 Scale-10 稳态验证后再 Scale-100 首批百人。

## 归属

- L1_domain_service: `runtime`
- L2_business_capability: `runtime-data-engineering`
- L3_story: `system-creator-pool`

## 范围

### In Scope

- CreatorBundle 单一真相源与三向物化（creator.yaml / user seed / relations seed）
- 五段对象树：`1.acquire` → `2.score` → `3.enrich` → `4.materialize` → `5.validate`
- `qwq-data governance creator-pool` CLI 与 `verify creator-scale-readiness`
- Scale-10（10 人）→ Scale-100（100 人）放量门禁

### Out of Scope

- 万级 metadata admin import（后续 CR）
- 实时外站爬虫生产环境调度

## 核心原则

1. 先 10 后 100，与内容工程 `s10verify → cs100verify` 同构
2. 规格/目录/测试冻结后才写业务 CLI
3. derivative persona，非 1:1 impersonation
4. CLI-first，禁止新增直跑业务脚本

## 设计摘录

### 目录对照（content vs creator）

| 内容工程 | 创作者工程 |
|---|---|
| `runtime/batches/{task}/{batch}/posts/` | `runtime/creator_pools/{vertical}/{batch}/creators/` |
| `1.download..5.review` | `1.acquire..5.validate` |
| `verify scale-readiness` | `verify creator-scale-readiness` |
| `templates/blueprints/` | `templates/creator_profiles/travel/{batchId}/` |
| `artifacts/s10verify_readiness.json` | `artifacts/creator_scale10_readiness.json` |

### CreatorBundle 物化

```text
CreatorBundle (4.materialize/creator_bundle.json)
  -> templates/creator_profiles/travel/{batch}/*.creator.yaml
  -> contracts/.../creator_pool/*.seed.json
  -> creator_relations.seed.json
```

### 运行时根与 CLI

- `QWQ_DATA_ROOT/runtime/creator_pools/travel/{batchId}/`
- 隔离验证：`~/qwq_creator_verify`
- `qwq-data governance creator-pool {plan,acquire,score,enrich,materialize,validate,seed,workflow,report}`
- `qwq-data verify creator-scale-readiness --vertical travel --batch ... --target 10|100`

## 参考

- `quwoquan_data/docs/creator_pool_pipeline_spec.md`
- `quwoquan_data/docs/content_pipeline_spec.md`
