# system-creator-pool

## 概述

批量旅行/摄影/旅行摄影交叉 AI 创作者生成管线：从公开作者信号衍生 persona，经五段对象树物化为可 seed 的 CreatorBundle，支撑 Scale-10 稳态验证、Scale-120 shard 验证，以及 canonical `1200 unique -> travel/photo 双 1000 view` 的商用主线。

## 归属

- L1_domain_service: `runtime`
- L2_business_capability: `runtime-data-engineering`
- L3_story: `system-creator-pool`

## 范围

### In Scope

- CreatorBundle 单一真相源与三向物化（creator.yaml / user seed / relations seed）
- Creator profile 元数据投影：短系统 ID、头像/封面 preset、名字、slogan、headline、bio、标签、垂类、内容偏好、实体/圈子关系与 seed/import 资格；发布面不包含地域/IP、来源、operations 或版本字段；slogan/bio 必须具备千级多样性，禁止同一骨架句式只替换名词，需通过唯一性、前后缀聚集度与高相似句对门禁，其中 slogan 两两相似度 `>=0.70` 的句对占比必须 `<1%`；头像/封面 preset 必须使用系统花瓣色 token，并覆盖人物头像、摄影符号、代表性风景与地标封面
- 五段对象树：`1.acquire` → `2.score` → `3.enrich` → `4.materialize` → `5.validate`
- `qwq-data governance creator-pool` CLI 与 `verify creator-scale-readiness`
- Scale-10（10 人）→ Scale-120 shard（120 unique / 双 100 view）→ canonical Scale-1200（10 shard 聚合）放量门禁
- 旅行 × 摄影 canonical 商用配比：`200 travel_primary + 200 photography_primary + 800 travel_photography_cross`，导出 `travel view=1000`、`photography view=1000`、`overlap=800`
- creator source registry：真实平台/图库/馆藏/旅游局/discovery 平台作为候选来源真相源，禁止 live acquisition 使用 example 域
- 四环境投递策略：alpha/beta/gamma 走 seed/fixture import 资产，prod 只生成 rollout/import dry-run 包与 tombstone/rollback 预备数据，不直接携带测试 fixture
- 发布级创作者资产包：`quwoquan_data/publish/creators` 与 `publish/tags` 平级，仅承载 `manifest.json` 与 `creators.jsonl`；来源、复杂 evidence 与运行时 operations 不进入发布用户 profile

### Out of Scope

- 万级 metadata admin import（后续 CR）
- 实时外站爬虫生产环境调度
- prod 未审批直接 apply

## 核心原则

1. 先 10 后 120 shard，再 1200 unique 聚合，并同步校验双 1000 vertical views，与内容工程放量门同构
2. 规格/目录/测试冻结后才写业务 CLI
3. derivative persona，非 1:1 impersonation
4. CLI-first，禁止新增直跑业务脚本
5. 交叉类创作者必须同时具备 `travel` 与 `photography` verticalRefs，并至少各有 1 个 `Topic/旅行/*` 与 `Topic/摄影/*` interest tag

## 设计摘录

### 目录对照（content vs creator）

| 内容工程 | 创作者工程 |
|---|---|
| `runtime/{phase}/{contentType}/{supplyMode}/{intentLabel}-{taskHash}__{batch}/posts/` | `.qwq_output/runtime/creator_pools/{vertical}/{batch}/creators/` |
| `1.download..5.review` | `1.acquire..5.validate` |
| `verify scale-readiness` | `verify creator-scale-readiness` |
| `templates/blueprints/` | `templates/creator_profiles/travel/{batchId}/` |
| `.qwq_output/artifacts/content_runs/**/scale_readiness.json` | `.qwq_output/artifacts/pools/creator/creator_scale10_readiness.json` |

### CreatorBundle 物化

```text
CreatorBundle / compact creator profile
  -> templates/creator_profiles/travel/{batch}/*.creator.yaml
  -> contracts/.../creator_pool/*.seed.json
  -> creator_relations.travel_photo_1k_v1.seed.json
  -> user_pool.creator_pool{.batch}.json
  -> creator_content{.batch}.seed.json
  -> .qwq_output/artifacts/pools/creator/creator_content_prod_rollout_dryrun{.batch}.json
  -> publish/creators/{manifest.json, creators.jsonl}
```

### 运行时根与 CLI

- `QWQ_OUTPUT_ROOT/runtime/creator_pools/{vertical}/{batchId}/`
- 隔离验证：`QWQ_OUTPUT_ROOT`（默认 `<repo>/.qwq_output/`，不写 HOME scratch 根）
- `qwq-data governance creator-pool {plan,acquire,score,enrich,materialize,validate,seed,workflow,publish-creators,report}`
- `qwq-data governance user-pool {media-presets build|verify,rebuild-prefab-users}`
- `qwq-data verify creator-scale-readiness --vertical travel --batch ... --target 10|120|1200`

## 参考

- `quwoquan_data/docs/creator_pool_pipeline_spec.md`
- `quwoquan_data/docs/content_pipeline_spec.md`
