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
├── seed/
├── trees/
├── runs/
├── publish/
├── out/
└── downloads/
```

其中：

- `runtime/specs/{spec_id}.yaml`：运行时 spec 真相源
- `runtime/seed/source_registry.yaml`：authority/content 双源平台注册表
- `runtime/seed/entity_catalog/*.ndjson`：实体目录真相源
- `runtime/seed/tag_catalog/*.ndjson`：标签目录真相源
- `runtime/seed/graph/*.ndjson`：entity-tag-post 关系真相源
- `runtime/trees/**`：运行时树真相源
- `runtime/runs/{spec_id}/discovery.json`
- `runtime/runs/{spec_id}/topic_tasks.ndjson`
- `runtime/runs/{spec_id}/topics/{topic_id}/...`
- `runtime/runs/{spec_id}/instruction_profile.json`
- `runtime/runs/{spec_id}/entities/{entity_id}/authority_profile.json`
- `runtime/runs/{spec_id}/entities/{entity_id}/authority_pool.ndjson`
- `runtime/runs/{spec_id}/entities/{entity_id}/content_pool.ndjson`
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
- `crawl instruction-build`
- `crawl entities-by-tag`
- `crawl authority-sync`
- `crawl content-discover`
- `crawl compose-post`
- `crawl feedback-extract`

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
python3 quwoquan_data/tools/cli.py crawl fetch-source --spec quwoquan_data/runtime/specs/real_public_examples_001.yaml --topic real_west_lake_article_001 --task-type article --source-id real_west_lake_article_source_001 --url "https://zh.wikivoyage.org/wiki/%E6%9D%AD%E5%B7%9E"
python3 quwoquan_data/tools/cli.py crawl fetch-source --spec quwoquan_data/runtime/specs/real_public_examples_001.yaml --topic real_west_lake_image_001 --task-type image --source-id real_west_lake_image_source_001 --url "https://commons.wikimedia.org/wiki/File:West_Lake_-_Hangzhou,_China.jpg"
python3 quwoquan_data/tools/cli.py crawl run-topic --spec quwoquan_data/runtime/specs/real_public_examples_001.yaml --topic real_west_lake_article_001 --targets alpha,gamma --dry-run
python3 quwoquan_data/tools/cli.py crawl run-topic --spec quwoquan_data/runtime/specs/real_public_examples_001.yaml --topic real_west_lake_image_001 --targets alpha,gamma --dry-run
python3 quwoquan_data/tools/cli.py crawl status --spec quwoquan_data/runtime/specs/real_public_examples_001.yaml
```

推荐的阶段包装命令：

```bash
python3 quwoquan_data/tools/cli.py data explore --query "四川 川西 旅行攻略" --regions "四川,川西" --entity-types "名胜风景区,人文史迹"
python3 quwoquan_data/tools/cli.py data baseline --spec-doc "specs/feature-tree/runtime/runtime-data-engineering/geo-content-trinity/spec.md" --design-doc "specs/feature-tree/runtime/runtime-data-engineering/geo-content-trinity/design.md" --acceptance-doc "specs/feature-tree/runtime/runtime-data-engineering/geo-content-trinity/acceptance.yaml" --workflow-doc "specs/feature-tree/runtime/runtime-data-engineering/geo-content-trinity/workflow.md" --command-matrix-doc "specs/feature-tree/runtime/runtime-data-engineering/geo-content-trinity/command-matrix.md" --catalog-config "specs/feature-tree/runtime/runtime-data-engineering/geo-content-trinity/config/geo_catalog_config.sichuan.yaml" --naming-rules "specs/feature-tree/runtime/runtime-data-engineering/geo-content-trinity/config/entity_naming_rules.yaml" --geo-band-rules "specs/feature-tree/runtime/runtime-data-engineering/geo-content-trinity/config/geo_band_rules.sichuan.yaml" --schema-files quwoquan_data/schema/geo_catalog_row.schema.json quwoquan_data/schema/entity_catalog_row.schema.json quwoquan_data/schema/tag_catalog_row.schema.json quwoquan_data/schema/authority_pool_row.schema.json quwoquan_data/schema/source_pool_row.schema.json
python3 quwoquan_data/tools/geo/build_geo_poi_catalog.py --config specs/feature-tree/runtime/runtime-data-engineering/geo-content-trinity/config/geo_catalog_config.sichuan.yaml --output quwoquan_data/runtime/seed/sichuan_chuanxi_attractions_catalog.ndjson
python3 quwoquan_data/tools/cli.py data build-entities-tags --catalog quwoquan_data/runtime/seed/sichuan_chuanxi_attractions_catalog.ndjson
python3 quwoquan_data/tools/cli.py data download --spec quwoquan_data/runtime/specs/sichuan_chuanxi_attractions_full.yaml --topics "poi_node_11405204678" --max-sources 40 --skip-content-discover
python3 quwoquan_data/tools/cli.py data source-fetch --batch-label "sichuan_catalog_20260512" --source-url "<url>" --page-title "<page title>" --catalog-topic "poi_node_11405204678" --catalog-name "海螺沟景区"
python3 quwoquan_data/tools/cli.py data normalize-build-extract-input --batch-label "sichuan_catalog_20260512" --source-md "<runtime/runs/.../source.md>" --catalog-topic "poi_node_11405204678" --catalog-name "海螺沟景区"
python3 quwoquan_data/tools/cli.py data normalize-validate-output --stage extract --result "<extract-result.json>"
python3 quwoquan_data/tools/cli.py data normalize-build-review-input --extract-result "<extract-result.json>"
python3 quwoquan_data/tools/cli.py data normalize-validate-output --stage review --result "<review-result.json>"
python3 quwoquan_data/tools/cli.py data normalize-build-authority-input --review-result "<review-result.json>"
python3 quwoquan_data/tools/cli.py data normalize-validate-output --stage authority --result "<authority-result.json>"
python3 quwoquan_data/tools/cli.py data normalize-compile-entities --batch-label "sichuan_catalog_20260512"
python3 quwoquan_data/tools/cli.py data entity-catalog-materialize --batch-label "sichuan_catalog_20260512" --catalog quwoquan_data/runtime/seed/sichuan_chuanxi_attractions_catalog.ndjson --output-name "normalized_entities.ndjson"
python3 quwoquan_data/tools/cli.py data process-content --spec quwoquan_data/runtime/specs/sichuan_chuanxi_attractions_001.yaml --topics "poi_way_299409723" --targets alpha,gamma
python3 quwoquan_data/tools/cli.py data publish --spec quwoquan_data/runtime/specs/sichuan_chuanxi_attractions_001.yaml --topics "poi_way_299409723"
bash scripts/reset_quwoquan_data_runtime_full.sh
bash scripts/run_sichuan_geo_content_trinity_e2e.sh
# 四川全量县级切片编排（需稳定网络；见脚本内环境变量说明）:
# bash scripts/run_sichuan_province_full_batch_trinity.sh
```

**目录口径**：`runtime/seed/chuanxi_attractions_catalog.yaml` 为 KPI-L1 **手工小集**（示例种子）；**≥1000 目录候选层**以 `build_geo_poi_catalog` 产出的 `sichuan_chuanxi_attractions_catalog.ndjson` 为准。地级切片：`geo_catalog_config.sichuan.yaml`；县级切片：`geo_catalog_config.sichuan.county.yaml`；刷新县级 `slices` 列表：`python3 quwoquan_data/tools/geo/list_admin_slices_overpass.py --province 四川省 --admin-level 6 --emit-yaml`。

## 10. 验收口径

- runtime 根为默认读写根
- 仓库验证可在无预置 runtime 数据下，通过 `tests/fixtures/runtime_seed/` 起临时 runtime
- `spec-discovery` 可初始化 topic 壳目录，不再依赖根目录旧 runs
- `fetch-source` 可把真实 URL 拉进 runtime
- `run-topic` 可在已有真实证据上自动补全默认 enrichment，并发布 package
- 真实性 gate 与 package gate 都能独立运行

## 11. schemaVersion 策略（Phase 1 / quwoquan_data）

**原则**

| 动作 | 规则 |
|------|------|
| **新写入** | 只允许**稳定字符串**常量（形如 `quwoquan_data.package_manifest`、`quwoquan_data.crawl_discovery`）；**禁止**新出现 `.vN` 后缀字符串。 |
| **读取校验** | 允许 `当前稳定常量 ∪ 兼容集合`。（例如 `COMPAT_DISCOVERY_SCHEMA_VERSIONS`） |
| **代码真相源** | 写入用到的 `*_SCHEMA_VERSION` 定义于 `tools/common.py`、`crawl_runtime_contract.py`、`source_registry.DEFAULT_SOURCE_REGISTRY` 等常量区；不得在业务代码手写第二套字面量路径。 |

**门禁**

- 仓库侧：`python3 scripts/verify_repo_schema_versions.py`（可加 `--prefix quwoquan_data/` 收窄）  
  对**许可路径**内的 JSON / 结构化 YAML 做递归解析：`schemaVersion` 为字符串且以 `.v`+阿拉伯数字结尾 → **fail**。`specs/`、feature-tree、changelog、契约 `metadata/**/tests/**` 等非 strict YAML、`tmp/`、`app_log/`、部分 JSON 等在脚本内排除，不参与解析。（`COMPAT_*` 仅见于 Python）
- CI / `make verify`：`verify_repo_schema_versions.py`（全仓）+ `verify_quwoquan_data.sh`（前缀 `quwoquan_data/` 快检，`make gate`/`run_app` 含全仓门禁）
- `--warn-only`：仅告警不失败，可供渐进收口期使用。

**全 monorepo（Phase 2）**  
App 环境包、合约 test fixtures、`deploy/shared` 与相关生成脚本中的 `schemaVersion` 已收口为**稳定名**。全仓硬门禁：`python3 scripts/verify_repo_schema_versions.py`（`make verify-repo-schema-versions`；已串联 `make verify` 与 `gate_repo.sh` 的 `run_app`）。`make verify-quwoquan-data` / `verify_quwoquan_data.sh` 内仍对 `quwoquan_data/` 前缀做同规则快检。

早期带 `.vN` 的取值仅允许留在 **Python `COMPAT_*`**（如 `quwoquan_data/tools/common.py`）供读盘兼容，**不得**再写入已跟踪的 YAML/JSON。

## 12. runtime 生成数据清理（Phase 3）

从 **默认** `quwoquan_data/runtime`（或 `QWQ_RUNTIME_ROOT`）删除生成目录：`runs/`、`publish/`、`out/`、`downloads/`，便于消除旧磁盘产物后再按 SPEC 重跑。

- **脚本**：`scripts/clean_quwoquan_data_runtime_generated.sh`（默认交互确认输入 `YES`；无人值守：`FORCE=1`）
- **Make**：`make clean-quwoquan-data-runtime-generated`（等价 `FORCE=1`）

**保留**：跟踪或需人工维护的 `runtime/specs/**`、`runtime/seed/**`、`runtime/trees/**` 等不删除；清理后可由下次 `ensure_runtime_layout`/`crawl` 命令按需重建空目录层级。

## 13. 成都 + 川西 E2E 验收与 KPI（Phase 4）

### 工具链闭环（小规模即可证明）

建议在固定 `spec_id`（示例：`chengdu_chuanxi_attractions_001`）下对齐下列顺序；大规模 discovery **建议 `--skip-hydrate`**，深验证任选 1～3 个 topic 做全量 hydrate：

```text
instruction-build → entity-catalog-build → spec-build → authority-sync → content-discover → content-hydrate → content-review → compose-post
```

（等价旧线也可用 `spec-discovery` / `run-topic`，见第 9 节。）

### K0 — 工程门禁

- `python -m unittest discover -s quwoquan_data/tests` 全绿。
- `python3 scripts/verify_repo_schema_versions.py`（或 `make verify-repo-schema-versions`）与 `make verify-quwoquan-data-schema-versions` 通过。

### K1 — 产物完整性（`chengdu_chuanxi_attractions_001`）

| 检查项 | 条件 |
|--------|------|
| discovery | `crawl spec-discovery --skip-hydrate` 写入 `runs/{spec_id}/discovery.json` 与 `topic_tasks.ndjson`；其中 `schemaVersion` ∈ `{稳定名 ∪ 兼容集合}` |
| 双源工作区（workflow） | `instruction_profile.json` 按需存在；抽样实体具备 `authority_pool.ndjson` / `content_pool.ndjson` |
| hydrate 抽样 | 至少 1 个 topic：`pages/**/source.md`（或等价）非空、无门禁报错 |
| content-review | 审核字段与 **`rewritePolicy`** 符合 [`workflow_ops.py`](tools/workflow_ops.py) 中的 `handle_content_review` |
| publish 包（若启用） | `manifest.json` 中 `schemaVersion` 写入 `quwoquan_data.package_manifest`（读写仍兼容早期值 `2`） |

### K2 — 数据质量（自动化 + 抽样）

- **相关性**：抽样 topic 标题/正文命中 `relevanceTokens` 或实体主名之一（与 `crawl_topic_pool.build_article_row` 一致）；`_page_authenticity_reasons.topic_relevance_miss` 占比 **抽样集 < 20%**（阈值可后续入库内脚本）。
- **精品占比**：在 `content-review` 已通过集合内，判定为精品（或等价高分/`rewritePolicy` 代理档位）约占 **≈30%**（容许偏差在验收记录中写明）。
- **双源分离**：百科/权威域 URL 入 authority/content 池的规则与 **`runtime/seed/source_registry.yaml`** / registry 常量一致。

### K3 — 覆盖 KPI（可选档位）

| 代码 | 含义 |
|------|------|
| **KPI-L1（回归）** | `chuanxi_attractions_catalog.yaml` 行集合不少于当前仓库跟踪基线 |
| **KPI-L2（扩展）** | 若启用外部 POI 枚举：成都+川西范围内 POI ≥ 约定阈值（如 1000），且每 POI 至少 1 条 authority 候选或已通过 content-review 的 content 候选 |
| **KPI-L3（分布监控）** | content 候选 p50/p90、hydrate 成功率、按域名分布——用于捕获「又回到仅 wiki」类回归 |

**川西 / 成都「全量景点 + 秘境」E2E 推荐**：以 OSM Overpass（或等价开放名录）在成都+川西范围导出 POI → `export-poi-topics` 生成 NDJSON/catalog → `entity-catalog-build` / `article_topic_catalog_ref` 与 `chengdu_chuanxi_attractions_001`（或等价 spec）对齐后跑整条双源链路。**大规模 discovery 使用 `--skip-hydrate`**；**深浅结合**：任选知名景区、城市公园、`trailhead` 等小众点共 3～5 例做全量 hydrate 与 `content-review`。  

**全量 KPI-L2 闸门**：进入 spec 的唯一实体 topic ≥ **1000**（或由数据可得性调整后写在验收表中并说明 bbox/tagging 取舍）；抽样 5%～10% POI：`authority_pool` 有可验证 URL 或可标记 `authority_pending`；Content 域名分布满足 KPI-L3。**手工 catalog**（如 `chuanxi_attractions_catalog.yaml`）仍作 **KPI-L1** 回归小集并行保留。

### K4 — 合规期望

旅行/社交媒体（马蜂窝、小红书、微博等）以 **robots/TOS + 站点反爬** 为准；工具链门禁验收以 **合规候选 URL、可审计元数据、可选导出**为主，不因「未到站可抓取」直接判失败——除非已有明确适配实现与法务结论。

## 14. 当前真实可重跑样例

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
