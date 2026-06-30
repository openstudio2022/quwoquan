# 阶段证据：开放许可图库适配（fix-image-gallery-sources）

特性树归属：`AppRoot -> 数据工程内容生产(L1) -> 图片作品内容生产(L2) -> 专业图库一源一作品(L3)`
验收意图：contract（来源类目/许可分流红线）；测试证据：`local_contract`。

## 目标

图片作品（画廊）必须一源一作品来自**专业图库**，按许可分流：
- 开放许可图库（CC/PD/开放商用）→ 可发布，必须记 license + termsUrl。
- 摄影社区（图虫/500px/Flickr/Behance）→ 须按平台条款逐图授权后入库。
- Pinterest / 摄影灵感站 → **仅编辑参考，禁止下载入库发布**。
- 未授权图片一律不可发布（不绕硬门）。

## 现状审视（metadata-first 已就位）

来源类目与许可分流的唯一真相源：`quwoquan_data/templates/_registry/catalogs/source_catalog.yaml`。

| categoryId | 含义 | 代表平台 | 可发布性 |
|---|---|---|---|
| `open_license` | 开放许可图库 | Wikimedia Commons / Unsplash / Pexels / Pixabay / Openverse / Rawpixel | 可发布（须 license+termsUrl，门校验 CC/PD 商用兼容） |
| `photography_platform` | 摄影作品平台/社区 | 图虫 / 500px / Flickr / Behance | 须逐图授权（platform aliases：tuchong/flickr/behance→此类） |
| `stock_authorized` | 授权图库 | Getty / Adobe Stock / 视觉中国授权 / 摄图网 | 须授权凭证 + usageScope |
| `museum_archive` | 博物馆/档案开放图像 | The Met / Rijksmuseum / Smithsonian Open Access | 须开放条款+机构署名 |
| `editorial_reference_only` | 仅编辑参考 | Pinterest / 小红书摄影灵感 / Behance参考 | **禁止入库发布**（不在 photography 准出核心类目） |

photography 垂直 `coreCategories: [open_license, photography_platform]` —— 图片作品准出核心类目**只**接受开放许可与摄影社区，`editorial_reference_only`/`stock_authorized` 绝不在准出核心类目内。

许可强制门（已存在、已接门禁）：
- `quwoquan_data/scripts/vertical/license.py::validate_image_rights`：按垂直 `license_policy.yaml` 校验 license 种类、AI 披露、usageScope。
- `_license_allows_app_publish`：CC NC/ND 不可发布；CC-BY/BY-SA/PD 商用兼容才放行。
- `test_image_collection_gate__local_contract_test.py`（含 `test_openverse_filters_nc_nd_and_keeps_publishable_license`）已在 `verify_quwoquan_data.sh`（行195）。

真实网络抓取适配器（开放许可发现层）：
- `wiki_media.py`：Wikimedia Commons（`_commons_images*` / `_wikidata_commons_images`）+ **Openverse**（`_openverse_images`，按 NC/ND/尺寸/相关性过滤，license URL 锁原始落地页）。Openverse 本身聚合索引 Unsplash/Flickr 等 CC 内容，已覆盖主流开放许可发现路径。

## 本阶段改动（离线、可验证）

新增"图片作品来源许可分流"红线契约测试，锁定 metadata-first 类目与受限平台标注：
- `quwoquan_data/tests/template/test_source_catalog.py::test_photography_image_work_sources_route_by_license_metadata_first`
  - open_license：Wikimedia Commons / unsplash / pexels / pixabay / openverse → `open_license`。
  - photography_platform：图虫 / tuchong / 500px / flickr / behance → `photography_platform`。
  - stock_authorized：Adobe Stock / depositphotos / 摄图网 → `stock_authorized`。
  - editorial_reference_only：Pinterest / pinterest / 小红书摄影灵感 → `editorial_reference_only`。
  - photography 准出核心类目恒为 `{open_license, photography_platform}`，断言 `editorial_reference_only`/`stock_authorized` 不在其中。

测试已随 `test_source_catalog.py`（`verify_quwoquan_data.sh` 行132）入门禁。

## 测试证据

```
$ python3 quwoquan_data/tests/template/test_source_catalog.py
PASS test_catalog_structure_is_valid
PASS test_coverage_accepts_quality_article_sources_without_travelogue
PASS test_coverage_blocks_single_category
PASS test_coverage_satisfied_when_diverse
PASS test_photography_image_work_sources_route_by_license_metadata_first
PASS test_platform_category_maps_vertical_sources
PASS test_unknown_platform_reported
PASS test_vertical_inference
source catalog tests passed (8)
```

## 如实标注的受限/待办（不绕硬门）

- **直连 Unsplash / Pexels / Pixabay API 适配器尚未接线**：当前开放许可发现仅 Wikimedia Commons + Openverse。直连三大图库 API 需各自 **API key + 联网**，属在线工作，无法离线 hermetic 验证；按纪律推迟到真实 agent/联网阶段（需先经 QWQ 凭据通道下发 key）。Openverse 已索引 Unsplash/Flickr 等 CC 内容，开放许可主路径不阻塞。
- **图虫/Pinterest 受限**：图虫=`photography_platform`（须逐图授权，未授权不可发布）；Pinterest=`editorial_reference_only`（仅参考，禁止入库发布）。已由 catalog 别名 + 准出核心类目 + 上述契约测试硬性约束，如实标注受限，未绕硬门。

## 剩余风险

- 直连商用图库 API 适配器待 key+联网阶段补齐；当前以 Commons+Openverse 覆盖开放许可主路径，许可强制门与受限标注已闭环。
