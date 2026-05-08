# quwoquan_data

`quwoquan_data` 现在采用的是一条 **commands-only** 主线：

`三棵树 -> batch_plan -> retrieval_plan -> raw -> publish -> out`

它不在 Python 代码里接真实搜索 provider，而是把搜索执行层收敛为：

- 模型先生成结构化检索条件
- Cursor commands 负责执行外部证据采集
- 所有证据必须显式落到 `raw/{batch_id}`
- `batch run --dry-run` 负责最终收口到 `publish/` 和 `out/`

## 结构速览

```text
quwoquan_data/
├── SPEC.md
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

## 核心原则

- `trees/entities/` 定义 `EntityFact`，不再把实体事实层直接投成 `Homepage`
- `trees/content/` 只定义趣我圈真实可发布内容模板，当前优先 `图片帖` 与 `文章帖`
- `trees/tags/` 是实体和内容都可复用的标准标签字典
- `batch_plan` 只描述批次目标与约束，`retrieval_plan` 才是每轮执行计划
- Python CLI 只做规划、校验、收口，不直接访问公网
- `publish/` 只放源数据，`out/` 只放环境 dry-run projection

## 当前样例

- `batch_plans/west_lake_image_001.yaml`：生成 `image/work` 图片帖
- `batch_plans/west_lake_article_001.yaml`：生成带 canonical `articleDocument` 的 `article/work` 文章帖
- `batch_plans/west_lake_loop_001.yaml`：演示两轮证据采集后再 finalize 的循环批次

## 命令式流程

### 1. 规划本轮检索

```bash
python3 quwoquan_data/tools/cli.py batch plan-retrieval \
  --plan quwoquan_data/batch_plans/west_lake_loop_001.yaml
```

这一步会生成：

- `raw/{batch_id}/retrieval_plan.json`
- `raw/{batch_id}/loop_state.json`

`retrieval_plan.json` 会给出：

- 主 query
- 分维度 `search_queries`
- 当前缺失的实体和标签
- 当前轮次的固定 prompt 契约

### 2. 落外部证据到 raw

由 Cursor commands 或手工执行检索，把结果显式写入：

- `raw/{batch_id}/search_results.ndjson`
- `raw/{batch_id}/pages.ndjson`
- `raw/{batch_id}/assets.ndjson`
- `raw/{batch_id}/facts.ndjson`

### 3. 查看批次状态

```bash
python3 quwoquan_data/tools/cli.py batch status \
  --plan quwoquan_data/batch_plans/west_lake_loop_001.yaml
```

状态输出会包含：

- 当前轮次
- 证据条数
- 缺失实体/标签
- 是否 `ready_for_finalize`
- 下一轮 query 数

### 4. 收口到 publish / out

```bash
python3 quwoquan_data/tools/cli.py batch run \
  --plan quwoquan_data/batch_plans/west_lake_article_001.yaml \
  --targets alpha,gamma \
  --dry-run
```

## 本地 smoke

```bash
bash scripts/verify_quwoquan_data.sh
```

## 产物位置

执行 `batch run` 后会生成：

- `publish/{batch_id}/entities.ndjson`
- `publish/{batch_id}/posts.ndjson`
- `publish/{batch_id}/summary.md`
- `out/{batch_id}/alpha_projection.json`
- `out/{batch_id}/gamma_projection.json`

## Cursor Commands

与这条命令式主线配套的编排文档：

- `.cursor/commands/crawl.md`
- `.cursor/commands/crawl-topic.md`

它们会围绕 `batch plan-retrieval -> raw 落证据 -> batch status -> batch run` 这一真实链路工作，不再引用旧的 `topics/runs/bundles` 模型。

详细规则见 `[SPEC.md](SPEC.md)`。
