# quwoquan_data 规格冻结

## 1. 目标

`quwoquan_data` 是趣我圈冷启动知识生产的独立工程区。当前版本只保留最小必要对象：

- 三棵事实树：`entities / content / tags`
- 一个批次计划：`batch_plan`
- 一个每轮检索计划：`retrieval_plan`
- 一组原始证据：`raw/`
- 一组源数据产物：`publish/`
- 一组环境干跑投影：`out/`

它的目标不是直接写入生产库，而是把“命令式证据采集 -> 结构化事实 -> Post 业务对象 -> 环境投影”这条链路跑通、跑轻、跑稳定。

## 2. 设计边界

- 不直接写生产数据库。
- 不替代 `quwoquan_service/contracts/metadata`，后者仍是 Post 字段、错误码和服务契约的唯一真相源。
- 不复制第三方原文进入最终发布正文；第三方页面只用于事实抽取、知识锚定和原创生成输入。
- 不再把实体事实层直接映射成 `Homepage`。
- 不在 Python 代码里接真实搜索 provider。
- 不恢复旧的 `topics/relations/catalogs/materials/runs/bundles/reports` 重型模型。

## 3. 目录模型

```text
quwoquan_data/
├── SPEC.md
├── README.md
├── pyproject.toml
├── schema/
├── trees/
│   ├── entities/
│   ├── content/
│   └── tags/
├── batch_plans/
├── raw/
├── publish/
├── out/
├── tools/
└── tests/
```

## 4. 三棵树定义

### 4.1 实体树

路径：`trees/entities/{实体大类}/{实体实例}.yaml`

实体节点定义的是 `EntityFact`，不是产品壳层对象。字段收敛为：

```yaml
entity_id:
name:
aliases: []
kind:
summary:
city:
address_text:
geo:
scene_tag_refs: []
category_tag_refs: []
media_refs: []
evidence_refs: []
search_terms: []
```

### 4.2 内容树

路径：`trees/content/{内容分组}/{内容模板}.yaml`

当前只保留：

- `trees/content/作品/图片帖.yaml`
- `trees/content/作品/文章帖.yaml`
- `trees/content/点滴/微趣帖.yaml`

模板字段：

```yaml
template_id:
label:
summary:
content_type:
content_identity:
required_post_fields: []
optional_post_fields: []
semantic_fields: []
```

### 4.3 标签树

路径：`trees/tags/{维度}/{标签}.yaml`

当前维度包括：

- `主题`
- `场景`
- `人群`
- `时间线`
- `质量`
- `风险`

标签字段保持极简：

```yaml
tag_id:
label:
summary:
parent_tag_ref:
```

## 5. batch_plan 与 retrieval_plan

### 5.1 batch_plan

路径：`batch_plans/{batch_id}.yaml`

`batch_plan` 只表达批次目标与约束，不直接承担每轮执行状态。当前字段：

```yaml
batch_id:
query:
search_provider: cursor_commands
allow_domains: []
fetch_top_k:
expansion_rounds:
content_type_ref:
creator_refs: []
entity_refs: []
tag_refs: []
target_envs: []
retrieval_context:
completion_policy:
publish_policy:
```

约束：

- `search_provider` 固定为 `cursor_commands`
- `creator_refs` 只引用 `user_pool.json` 中已有的 `fixture_user_*`
- `entity_refs` / `tag_refs` 直接引用三棵树
- `target_envs` 只表达干跑目标

### 5.2 retrieval_plan

路径：`raw/{batch_id}/retrieval_plan.json`

`retrieval_plan` 是每轮真正要执行的检索计划。它参考 assistant-service 的 reasoning JSON 契约，但执行层不是云端 search provider，而是 Cursor commands。

固定字段：

```json
{
  "query": "主检索短词",
  "search_queries": [
    {
      "dimension": "实体补齐",
      "query": "西湖亲子友好酒店 杭州西湖 半日路线",
      "purpose": "补齐缺失实体证据",
      "entity_refs": ["trees/entities/住宿/西湖亲子友好酒店.yaml"],
      "tag_refs": [],
      "target_domains": ["you.ctrip.com"],
      "round": 2,
      "status": "pending"
    }
  ],
  "location": "杭州",
  "location_search_name": "Hangzhou",
  "target_domains": ["mafengwo.cn", "you.ctrip.com"],
  "round": 2,
  "status": "planned"
}
```

## 6. raw / publish / out

### 6.1 raw

路径：`raw/{batch_id}/`

固定文件如下：

- `search_results.ndjson`
- `pages.ndjson`
- `assets.ndjson`
- `facts.ndjson`
- `loop_state.json`
- `retrieval_plan.json`

各文件字段约束：

- `search_results.ndjson`：`query/domain/url/title/snippet/round/collector`
- `pages.ndjson`：`url/title/plain_text/fetched_at/round/evidence_hash`
- `assets.ndjson`：`asset_id/object_key/source_url/caption/round`
- `facts.ndjson`：`fact_id/source_url/title/entity_refs/tag_refs/.../round`
- `loop_state.json`：当前轮次、停止原因、下一轮 query、是否已完成

### 6.2 publish

路径：`publish/{batch_id}/`

固定产物：

- `entities.ndjson`
- `posts.ndjson`
- `summary.md`

其中：

- `entities.ndjson` 写入 `EntityFact`
- `posts.ndjson` 每条记录都采用 `post_payload + semantic` 双层结构

### 6.3 out

路径：`out/{batch_id}/`

`out/` 只表达环境干跑投影，当前按目标环境生成：

- `alpha_projection.json`
- `gamma_projection.json`

## 7. 命令式自动化主线

唯一主线如下：

```text
batch_plan -> batch plan-retrieval -> raw evidence append -> batch status -> batch run --dry-run -> publish/out
```

这里的“检索执行”由 Cursor commands 完成，不由 Python 代码直接请求公网。

## 8. CLI 范围

当前 CLI 保留三类命令：

- `tree validate`
- `batch plan-retrieval`
- `batch status`
- `batch run`

执行入口：

```bash
python3 quwoquan_data/tools/cli.py tree validate --tree all
python3 quwoquan_data/tools/cli.py batch plan-retrieval --plan quwoquan_data/batch_plans/west_lake_loop_001.yaml
python3 quwoquan_data/tools/cli.py batch status --plan quwoquan_data/batch_plans/west_lake_loop_001.yaml
python3 quwoquan_data/tools/cli.py batch run --plan quwoquan_data/batch_plans/west_lake_article_001.yaml --targets alpha,gamma --dry-run
```

## 9. Cursor Commands

命令式编排文档：

- `.cursor/commands/crawl.md`
- `.cursor/commands/crawl-topic.md`

它们必须围绕当前真实 CLI 和 `raw/{batch_id}` 状态工作，不允许再引用旧的 `topics/runs/bundles` 模型。

## 10. 停止条件与验收

完成一批任务的条件：

1. `required entity_refs` 已在 `facts.ndjson` 中全部覆盖
2. `required tag_refs` 已在 `facts.ndjson` 中全部覆盖
3. `fact_count`、`evidence_url_count`、`perspective_count` 达到 `completion_policy`
4. `batch run --dry-run` 通过，并产出 `publish/`、`out/`
5. 若连续一轮没有新增高价值 query，或已达到 `expansion_rounds` 上限，则可以进入 `exhausted`

验收标准：

- `quwoquan_data` 内没有真实 search provider 实现
- 模型主导检索条件被固化为稳定 prompt 契约
- `/crawl` 与 `/crawl-topic` 已对齐当前 `batch_plan/raw/publish/out` 真相源
- 至少一个批次能完成两轮命令式采集并最终通过 `batch run --dry-run`
- 所有外部证据都能在 `raw/{batch_id}` 下追溯到来源 URL 与轮次
# quwoquan_data 规格冻结

## 1. 目标

`quwoquan_data` 是趣我圈冷启动知识生产的独立工程区。当前版本只保留最小必要对象：

- 三棵事实树：`entities / content / tags`
- 一个搜索优先的 `batch_plan`
- 一组原始样本：`raw/`
- 一组源数据产物：`publish/`
- 一组环境干跑投影：`out/`

它的目标不是直接写入生产库，而是把“原始内容样本 -> 实体事实 -> Post 业务对象 -> 环境投影”这条链路先跑通、跑轻、跑稳定。

## 2. 设计边界

- 不直接写生产数据库。
- 不替代 `quwoquan_service/contracts/metadata`，后者仍是 Post 字段、错误码和服务契约的唯一真相源。
- 不复制第三方原文进入最终发布正文；第三方页面只用于事实抽取、知识锚定和原创生成输入。
- 不再把实体事实层直接映射成 `Homepage`。
- 不引入 `topics/relations/catalogs/materials/runs/bundles/reports` 这些重型中间层。

## 3. 目录模型

```text
quwoquan_data/
├── SPEC.md
├── README.md
├── pyproject.toml
├── schema/
├── trees/
│   ├── entities/
│   ├── content/
│   └── tags/
├── batch_plans/
├── raw/
├── publish/
├── out/
├── tools/
└── tests/
```

## 4. 三棵树定义

### 4.1 实体树

路径：`trees/entities/{实体大类}/{实体实例}.yaml`

实体节点定义的是 `EntityFact`，不是产品壳层对象。字段收敛为：

```yaml
entity_id:
name:
aliases: []
kind:
summary:
city:
address_text:
geo:
scene_tag_refs: []
category_tag_refs: []
media_refs: []
evidence_refs: []
search_terms: []
```

这类对象用于四个场景：

1. 搜索与抓取时的知识锚点
2. 内容生成时的语义挂接对象
3. 推荐和检索时的实体召回对象
4. 未来如需进入产品治理，再额外适配到壳层对象

### 4.2 内容树

路径：`trees/content/{内容分组}/{内容模板}.yaml`

内容树定义的是“趣我圈可发布业务内容类型模板”，不是抽象文体树。当前只保留：

- `trees/content/作品/图片帖.yaml`
- `trees/content/作品/文章帖.yaml`
- `trees/content/点滴/微趣帖.yaml`（预留）

模板字段收敛为：

```yaml
template_id:
label:
summary:
content_type:
content_identity:
required_post_fields: []
optional_post_fields: []
semantic_fields: []
```

### 4.3 标签树

路径：`trees/tags/{维度}/{标签}.yaml`

标签树是实体和内容共用的标准字典，当前维度包括：

- `主题`
- `场景`
- `人群`
- `时间线`
- `质量`
- `风险`

标签字段保持极简：

```yaml
tag_id:
label:
summary:
parent_tag_ref:
```

## 5. batch_plan 定义

路径：`batch_plans/{batch_id}.yaml`

`batch_plan` 是当前唯一需要人工维护的执行计划对象。它直接表达一次内容生产批次的搜索入口、知识锚点、内容模板、运营账号和目标环境。

字段如下：

```yaml
batch_id:
query:
search_provider:
allow_domains: []
fetch_top_k:
expansion_rounds:
content_type_ref:
creator_refs: []
entity_refs: []
tag_refs: []
target_envs: []
publish_policy:
```

设计原则：

- 以 `query` 和 `search_provider` 驱动搜索优先流程
- `creator_refs` 只引用 `user_pool.json` 里的既有 `fixture_user_*`
- `entity_refs` / `tag_refs` 直接引用三棵树，不再通过主题树转译
- `target_envs` 只表达干跑目标，不污染 `publish/`

## 6. raw / publish / out

### 6.1 raw

路径：`raw/{batch_id}/`

固定只保留四类文件：

- `search_results.ndjson`
- `pages.ndjson`
- `assets.ndjson`
- `facts.ndjson`

含义：

- `search_results`：搜索发现层
- `pages`：抓回来的页面文本快照
- `assets`：图片等资源引用
- `facts`：供内容生成消费的结构化事实

### 6.2 publish

路径：`publish/{batch_id}/`

`publish/` 必须直接对齐趣我圈业务对象，不再生成 `post_drafts`、`bundle manifest` 之类的中间格式。当前固定产物：

- `entities.ndjson`
- `posts.ndjson`
- `summary.md`

其中：

- `entities.ndjson` 写入 `EntityFact`
- `posts.ndjson` 每条记录都采用 `post_payload + semantic` 双层结构

示意：

```json
{
  "post_payload": {
    "contentType": "image",
    "contentIdentity": "work",
    "title": "杭州西湖傍晚这样走最舒服",
    "body": "……",
    "mediaUrls": ["media/image/post/..."],
    "coverUrl": "media/image/post/...",
    "tags": ["theme_city_walk"],
    "authorId": "fixture_user_photo",
    "authorDisplayNameSnapshot": "契约摄影作者"
  },
  "semantic": {
    "entity_refs": ["trees/entities/地点/西湖.yaml"],
    "tag_refs": ["trees/tags/主题/城市漫游.yaml"],
    "source_urls": ["https://..."]
  }
}
```

### 6.3 out

路径：`out/{batch_id}/`

`out/` 只表达环境干跑投影，当前按目标环境生成：

- `alpha_projection.json`
- `gamma_projection.json`

它只回答三个问题：

1. 这个批次会投影哪些实体
2. 会投影哪些帖子
3. 会带上哪些资源引用

## 7. 自动化主线

唯一主线如下：

```text
batch_plan -> raw/search_results -> raw/pages -> raw/facts -> publish/entities.ndjson + publish/posts.ndjson -> out/*_projection.json
```

当前 `batch run` 不再调用旧的 `materials/crawl/bundle` 命令链。

## 8. CLI 范围

当前 CLI 只保留两类命令：

- `tree validate`
- `batch run`

执行入口：

```bash
python3 quwoquan_data/tools/cli.py tree validate --tree all
python3 quwoquan_data/tools/cli.py batch run --plan quwoquan_data/batch_plans/west_lake_image_001.yaml --targets alpha,gamma --dry-run
python3 quwoquan_data/tools/cli.py batch run --plan quwoquan_data/batch_plans/west_lake_article_001.yaml --targets alpha,gamma --dry-run
```

## 9. 验收标准

- 实体事实定义已与 `Homepage` 解耦
- `trees/` 只剩 `entities/content/tags`
- `batch_plan` 是搜索优先的唯一执行入口
- `publish/` 能输出真实 `Post` payload 与 `semantic` 关联
- `图片帖` 与 `文章帖` 都能生成可验证样例
- `out/` 只做环境 dry-run，不混入源数据
