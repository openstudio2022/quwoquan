# 命令矩阵：geo-content-trinity

## 1. 原则

- 对外优先使用显式 `data *` 阶段命令
- 对内复用 `crawl *` 与验证脚本，不复制实现
- 每条命令必须定义：输入、输出、失败重试、准出与上游依赖
- **四川扩展批次（R7）**：实体可经「百科/维基权威轨」或「≥2 篇 post 互证轨」准入；后者须在 `build-entities-tags` / `download` / `process-content` 边界写清字段与准出（见 `spec.md` A15–A18）

## 2. 外部阶段命令 → 内部执行原语


| 外部命令                                                              | 阶段        | 内部命令 / 脚本                                                                                                                                                                                                                                |
| ----------------------------------------------------------------- | --------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `python3 quwoquan_data/tools/cli.py data explore ...`             | 数据规格探索阶段  | 规格收敛与可选探测脚本                                                                                                                                                                                                                              |
| `python3 quwoquan_data/tools/cli.py data baseline ...`            | 数据规格基线阶段  | 文档 / 配置 / schema 存在性；可选 `--geo-band-rules`，与 `--catalog-config` 同传时校验与 `geo_band_rules_path` 解析一致                                                                                                                                           |
| `python3 quwoquan_data/tools/cli.py data build-entities-tags ...` | 生成实体和标签阶段 | `build_geo_poi_catalog`、`merge_overpass_poi_catalog`、`semantic_entity_resolution`、`crawl tag-catalog-build`、`crawl entity-catalog-build`                                                                                               |
| `python3 quwoquan_data/tools/cli.py data download ...`            | 下载与来源发现阶段 | `crawl instruction-build`、`crawl entities-by-tag`、`crawl spec-build`、`crawl authority-sync`、`crawl authority-review`、`crawl pool-bootstrap`、`crawl spec-discovery`、`crawl fetch-source`、`crawl content-discover`、`crawl content-hydrate` |
| `python3 quwoquan_data/tools/cli.py data process-content ...`     | 图文加工阶段    | `crawl content-review`、`crawl compose-post`、`crawl review-generated`                                                                                                                                                                     |
| `python3 quwoquan_data/tools/cli.py data publish ...`             | 发布与反馈阶段   | `crawl publish-approved`、`crawl feedback-extract`、`crawl feedback-verify`、`verify_quwoquan_data_source_authenticity.py`、`verify_quwoquan_data_post_packages.py`                                                                          |
| `python3 quwoquan_data/tools/cli.py data normalize-compile-entities ...` | 语义物化辅助命令 | `compile_entity_resolution.compile_batch`                                                                                                                                                                                                  |
| `python3 quwoquan_data/tools/cli.py data entity-catalog-materialize ...` | 语义物化辅助命令 | `compile_entity_resolution.materialize_entity_catalog`                                                                                                                                                                                     |


## 3. 输入 / 输出 / 准出

### 3.0 `data baseline`

**输入（节选）**

- `spec.md` / `design.md` / `acceptance.yaml` / `workflow.md` / `command-matrix.md`
- `--catalog-config`：`geo_catalog_config*.yaml`
- `--naming-rules`：`entity_naming_rules.yaml`
- `--geo-band-rules`：与 catalog 中 `geo_band_rules_path` 相对于 catalog 目录解析结果**同一文件**（同传时 CLI 强制对齐）
- `--schema-files`：geo / entity / tag / authority / source 等 row schema

**输出**：基线 JSON（`stage: data-baseline`，含各文件绝对路径）。

### 3.1 `data build-entities-tags`

**输入**

- `geo_catalog_config.yaml`
- `entity_naming_rules.yaml`
- Overpass JSON（可选）
- `runtime/trees/tags/**`

**输出**

- `runtime/seed/*_catalog.ndjson`
- `runtime/out/reports/*_slice_report.json`（同时镜像为 `runtime/seed/*_catalog.slice_report.json` 以满足门禁）
- `runtime/seed/entity_catalog/semantic_cluster_candidates.ndjson`
- `runtime/seed/entity_catalog/semantic_cluster_pending.ndjson`
- `runtime/seed/entity_catalog/*.ndjson`
- `runtime/seed/tag_catalog/*.ndjson`

**准出**

- `scripts/verify_geo_catalog_quality.py`
- `scripts/verify_catalog_entity_consistency.py`

### 3.1A `data normalize-compile-entities`

**输入**

- `runs/<batch>/normalization/results/extract/*.json`
- `runs/<batch>/normalization/results/review/*.json`
- `runs/<batch>/normalization/results/authority/*.json`
- `runs/<batch>/normalization/results/escalate/*.json`（可选）

**输出**

- `runs/<batch>/normalization/compiled/entity_resolution.ndjson`
- `runs/<batch>/normalization/compiled/pending_resolution.ndjson`
- `runs/<batch>/normalization/compiled/image_resolution.ndjson`

**准出**

- `entity_resolution` 中 `mainEntity + members + aliases` 结构可被 `entity-catalog-materialize` 消费

### 3.1B `data entity-catalog-materialize`

**输入**

- `runs/<batch>/normalization/compiled/entity_resolution.ndjson`
- 当前批次 `catalog.ndjson`

**输出**

- `runtime/seed/entity_catalog/<output_name>.ndjson`

**准出**

- 输出实体具备 `admissionTrack` / `evidenceArticleUrls` / `conflictCheckStatus` / `members`
- 仅 publishable 主实体进入顶层实体层

### 3.2 `data download`

**输入**

- `instruction_profile.json`
- `runtime/specs/*.yaml`
- `entity_catalog`
- `tag_catalog`

**输出**

- `authority_pool.ndjson`
- `source_pool.ndjson`
- `pages/**/source.md`

**准出**

- `validate_crawl_spec`
- hydrate 失败率统计

### 3.3 `data process-content`

**输入**

- `source_pool.ndjson`
- `pages/**/source.md`

**输出**

- 审核后 pool
- `compose_summary.json`
- `audit_summary.json`

**准出**

- review schema 校验
- 实体锚点抽样一致性

### 3.4 `data publish`

**输入**

- 审核通过的 pool / compose / audit 结果

**输出**

- `publish/**`
- `review.json`
- feedback ndjson

**准出**

- `scripts/verify_quwoquan_data_source_authenticity.py`
- `scripts/verify_quwoquan_data_post_packages.py`

## 4. 兼容命令

- `data build-content` 保留为兼容别名，统一委托到 `data process-content`
- 兼容命令不应再出现在新文档的主示例中

## 5. 辅助脚本

| 脚本 | 作用 |
|---|---|
| `bash scripts/reset_quwoquan_data_runtime_full.sh` | 清空当前 runtime 并恢复 tracked baseline |
| `bash scripts/run_sichuan_geo_content_trinity_e2e.sh` | 以四川样例 seed 执行 full reset 后端到端验证 |
| `bash scripts/run_sichuan_province_full_batch_trinity.sh` | 四川县级切片重建目录（≥MIN_KEPT）、全量 `skip-hydrate`、分批 hydrate/process/publish |
| `python3 quwoquan_data/tools/geo/list_admin_slices_overpass.py` | 从 Overpass 枚举 `admin_level` 行政区名，更新 `geo_catalog_config` 的 `scope.slices` |