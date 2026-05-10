# quwoquan_data

`quwoquan_data` 已切到 **代码与运行时分离** 的形态：

- 仓库内只保留 `schema/`、`tools/`、`tests/`、`README.md`、`SPEC.md`
- 真实运行数据统一写入 ignored 根目录 `quwoquan_data/runtime/`
- 测试样例统一收敛到 `quwoquan_data/tests/fixtures/`

默认路径解析：

- `QWQ_DATA_ROOT` 默认指向 `quwoquan_data/`
- `QWQ_RUNTIME_ROOT` 默认指向 `quwoquan_data/runtime/`

## 目录治理

```text
quwoquan_data/
├── README.md
├── SPEC.md
├── schema/
├── tools/
├── tests/
│   └── fixtures/
└── runtime/          # ignored，仅承载真实运行数据
```

`runtime/` 下的正式结构：

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

- `runtime/specs/{spec_id}.yaml` 是运行时 spec 真相源
- `runtime/trees/**` 是运行时实体/标签/模板树
- `runtime/runs/{spec_id}/topics/{topic_id}/...` 是 topic 工作区
- `runtime/downloads/` 存放原生抓取的 HTML 与图片二进制
- `tests/fixtures/runtime_seed/` 只保留测试种子，不再把样例 runs/publish/raw 跟踪到仓库根

唯一有效的 publish 真相源是：

- `quwoquan_data/runtime/publish/`

仓库根旧目录 `quwoquan_data/publish/`、`quwoquan_data/runs/`、`quwoquan_data/raw/`、`quwoquan_data/out/`、`quwoquan_data/crawl_specs/`、`quwoquan_data/trees/` 仅作为迁移中的待删除对象，不再参与当前主线读写。

## hybrid 主线

`/crawl` 与 `cli.py crawl *` 现在采用 hybrid 结构：

1. 命令编排层：
   - `crawl spec-discovery`
   - `crawl status`
   - `crawl run-topic`
2. tools 原生能力：
   - `crawl fetch-source`
   - HTML 拉取
   - 正文抽取
   - 图片 URL 抽取与下载
   - 元数据提取
   - 真实性 / 合规门禁

也就是说，command 层负责编排 spec/topic 生命周期，`tools/native_fetch.py` 负责最小真实 I/O。

## 常用命令

```bash
python3 quwoquan_data/tools/cli.py tree validate --tree all
python3 quwoquan_data/tools/cli.py crawl tag-catalog-build
python3 quwoquan_data/tools/cli.py crawl entity-catalog-build --catalog quwoquan_data/runtime/seed/chuanxi_attractions_catalog.yaml
python3 quwoquan_data/tools/cli.py crawl instruction-build --spec-id travel_seed_001 --instruction "成都 川西 旅行攻略与图片" --verticals travel --tag-refs trees/tags/主题/旅行攻略.yaml --content-modes article,image
python3 quwoquan_data/tools/cli.py crawl entities-by-tag --spec-id travel_seed_001 --tag-refs trees/tags/主题/旅行攻略.yaml
python3 quwoquan_data/tools/cli.py crawl spec-build --spec-id travel_seed_001
python3 quwoquan_data/tools/cli.py crawl authority-sync --spec quwoquan_data/runtime/specs/travel_seed_001.yaml
python3 quwoquan_data/tools/cli.py crawl content-discover --spec quwoquan_data/runtime/specs/travel_seed_001.yaml --seed quwoquan_data/runtime/seed/travel_urls_by_topic.ndjson
python3 quwoquan_data/tools/cli.py crawl content-hydrate --spec quwoquan_data/runtime/specs/travel_seed_001.yaml
python3 quwoquan_data/tools/cli.py crawl content-review --spec quwoquan_data/runtime/specs/travel_seed_001.yaml
python3 quwoquan_data/tools/cli.py crawl compose-post --spec quwoquan_data/runtime/specs/travel_seed_001.yaml
python3 quwoquan_data/tools/cli.py crawl review-generated --spec quwoquan_data/runtime/specs/travel_seed_001.yaml
python3 quwoquan_data/tools/cli.py crawl publish-approved --spec quwoquan_data/runtime/specs/travel_seed_001.yaml
python3 quwoquan_data/tools/cli.py crawl feedback-extract --spec quwoquan_data/runtime/specs/travel_seed_001.yaml
python3 quwoquan_data/tools/cli.py crawl feedback-verify --spec quwoquan_data/runtime/specs/travel_seed_001.yaml
python3 quwoquan_data/tools/cli.py crawl spec-discovery --spec quwoquan_data/runtime/specs/real_public_examples_001.yaml
python3 quwoquan_data/tools/cli.py crawl fetch-source --spec quwoquan_data/runtime/specs/real_public_examples_001.yaml --topic real_west_lake_article_001 --task-type article --source-id real_west_lake_article_source_001 --url "https://zh.wikivoyage.org/wiki/%E6%9D%AD%E5%B7%9E" --title "第一次逛杭州，先把西湖这条线走顺" --query "杭州 西湖 旅行指南 步行" --snippet "中文 Wikivoyage 杭州词条把西湖、湖滨和城市步行节奏写成了旅行指南，更适合重组为用户可读长文。" --rights-status clear --watermark-status clean
python3 quwoquan_data/tools/cli.py crawl fetch-source --spec quwoquan_data/runtime/specs/real_public_examples_001.yaml --topic real_west_lake_image_001 --task-type image --source-id real_west_lake_image_source_001 --url "https://commons.wikimedia.org/wiki/File:West_Lake_-_Hangzhou,_China.jpg" --title "雷峰塔视角下的西湖开阔湖面" --query "West Lake Hangzhou Commons image" --snippet "真实来源基于 Wikimedia Commons 文件页，来源页明确写出作者、拍摄时间和 CC BY-SA 3.0 授权。" --rights-status clear --watermark-status clean
python3 quwoquan_data/tools/cli.py crawl run-topic --spec quwoquan_data/runtime/specs/real_public_examples_001.yaml --topic real_west_lake_article_001 --targets alpha,gamma --dry-run
python3 quwoquan_data/tools/cli.py crawl run-topic --spec quwoquan_data/runtime/specs/real_public_examples_001.yaml --topic real_west_lake_image_001 --targets alpha,gamma --dry-run
python3 quwoquan_data/tools/cli.py crawl status --spec quwoquan_data/runtime/specs/real_public_examples_001.yaml
# 大 POI / 大 source_pool：先写池再轻量刷新 discovery（跳过逐条 hydrate）
python3 quwoquan_data/tools/cli.py crawl pool-bootstrap --spec quwoquan_data/runtime/specs/chengdu_chuanxi_attractions_001.yaml --merge
python3 quwoquan_data/tools/cli.py crawl spec-discovery --spec quwoquan_data/runtime/specs/chengdu_chuanxi_attractions_001.yaml --skip-hydrate
# Overpass JSON → topic NDJSON（供 spec.article_topic_catalog_ref）
python3 quwoquan_data/tools/cli.py crawl export-poi-topics --input /path/to/overpass.json --output quwoquan_data/runtime/seed/poi_topics.ndjson
```

说明：

- 双源主线现已拆成：
  - authority lane：`authority-sync` / `authority-review`
  - content lane：`content-discover` / `content-hydrate` / `content-review`
  - publish lane：`compose-post` / `review-generated` / `publish-approved`
  - feedback lane：`feedback-extract` / `feedback-verify`
- `instruction-build` 会把当前用户意图写成 `runtime/runs/{spec_id}/instruction_profile.json`，后续内容发现、评分与 rewritePolicy 都以它为最高优先级配置。
- `entity-catalog-build` / `tag-catalog-build` / `entities-by-tag` 负责“标签 -> 全量实体”的主链；长期真相源不再只靠 spec 里的 `entity_refs/tag_refs`。
- `content-review` 会把通过审核的内容候选桥接回 topic 工作区 `source_pool.ndjson`，从而复用现有 `compose-topic` / `audit-topic` 的发布链路。
- `run-topic` 现在会基于 retained 且通过真实性校验的来源，自动补全默认 `enrichment.ndjson` 字段（`selectedCandidateIds`、`sourceUrls`、`coverAssetId`、`figureAssetIds/mediaAssetIds`、`publishReady` 等），不再要求手工改 NDJSON 才能跑通真实样例。
- 当前本地真实可验证 publish 样例位于：
  - `quwoquan_data/runtime/publish/real_west_lake_article_001/`
  - `quwoquan_data/runtime/publish/real_west_lake_image_001/`

## 本地验证

```bash
bash scripts/verify_quwoquan_data.sh
python3 scripts/verify_quwoquan_data_source_authenticity.py
python3 scripts/verify_quwoquan_data_post_packages.py
python3 -m unittest discover -s quwoquan_data/tests
```

详细约束见 `quwoquan_data/SPEC.md`。