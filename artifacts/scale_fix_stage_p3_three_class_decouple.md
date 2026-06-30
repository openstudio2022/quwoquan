# P3 三类解耦（第一批）：实体主页主源=百科 + 文章含视频则放弃

规划真相源：`/Users/zhaoyuxi/.cursor/plans/提示词重构与三类解耦放量_2f1c2e11.plan.md`（P3）。

## 目标（P3 判据）

- 实体（entity homepage）：base draft 主源 **只来自百科**（维基/百度/搜狗百科），官网/官方/政务/媒体一律降为 supporting（可补事实、不得作 primaryEvidenceRef / 不得 seed base draft）。
- 文章（article）：图文混排（≥200 字）或长文（≥600 字）且必须有标题；**来源含内联视频则放弃**（不把视频内容强行图文化成攻略文章，避免成稿与原文严重不符）。
- 图片（image）：专业图库图文分离、标题可选（既有判据保留，P4 接入真实图库）。
- download：按内容类型路由、分类型下发调度（hasVideo 元数据持久化为文章弃稿提供依据）。

## 本批改动（metadata-first）

### P3-1 实体主页主源【只限百科】

- `quwoquan_data/templates/_registry/catalogs/content_source_registry.yaml`
  - homepage `primarySourceClasses: [encyclopedia]`；`knowledge_graph` / `official_site` 移入 `supportingOnlySourceClasses`；`promptFacts` 同步收紧。
- `quwoquan_data/scripts/build/homepage_text.py`
  - `_HOMEPAGE_PRIMARY_KIND_BONUS` 只保留百科类；官网/官方/政务进 `_HOMEPAGE_SUPPORT_ONLY_MARKERS`（priority 归 0）；`_homepage_source_priority` 仅在 `category == encyclopedia` 或命中百科 marker 时授予 primary。
- `quwoquan_data/scripts/download/research/source_quality.py`
  - `_HOMEPAGE_PRIMARY_SOURCE_MARKERS` 只保留百科；官网/官方/媒体进 `_HOMEPAGE_SUPPORT_ONLY_SOURCE_MARKERS`；`_homepage_can_seed_base_draft` 仅百科类目可 seed 主页 base draft。

### P3-2 文章【含视频则放弃】

- `quwoquan_data/scripts/download/fetch.py`
  - 新增 `html_has_inline_video()`（原生 `<video>` / `<source type=video/*>` / 主流视频站 iframe·embed 嵌入：B 站/YouTube/腾讯/优酷/爱奇艺/抖音/西瓜/Vimeo 等）。
- `quwoquan_data/scripts/_common/source_unit.py`
  - `write_source_unit(..., has_video: bool=False)`；manifest（meta.json）持久化 `hasVideo`。
- `quwoquan_data/scripts/download/handler_fetch.py`
  - 抓取后从 HTML（或 fetched_text）计算 `page_has_video`，传入 `write_source_unit`。
- `quwoquan_data/scripts/task/run.py`
  - 两处文章枚举路径：`meta.hasVideo` 为真即 `contains_video` 弃稿（不进文章候选）。

## 测试证据（local_contract）

- 新增 `quwoquan_data/tests/local_contract/common/test_three_class_decouple__local_contract_test.py`
  - `html_has_inline_video` 正/负例（video/source/iframe 站点 vs 纯图文）。
  - `_homepage_source_priority`：百科 primary（>0）、官网/政务 supporting（≤0）。
  - `_homepage_can_seed_base_draft`：仅百科可 seed。
  - `write_source_unit` 持久化 `hasVideo`（True/False）。
- 已接入 `quwoquan_data/scripts/verify/verify_quwoquan_data.sh`。
- 回归：`test_content_plan_source_gate / test_auto_content_plan / test_content_plan_distribution / test_source_quality_gate / test_auto_research_article_homepage` 全绿（47 passed）。

### P3-3 download 去实体键控按内容类型路由 + 分类型下发调度

现状盘点（已物理解耦的部分）：
- 三类来源计划物理分离：`homepage_source_plan.json` / `article_source_plan.json` / `image_source_plan.json`（`source_inputs.RESEARCH_PLAN_FILES`）。
- lane-scoped 抓取/选图：`download_fetch --lane {homepage,article,image}`、`_curated_sources_for_lanes`、`curated_images_for_entity(research_lane=...)`、lane-scoped source unit。

本批补齐（去「全部当 article」实体键控默认）：
- `quwoquan_data/scripts/download/source_inputs.py`
  - 新增 `LANE_CONTENT_TYPE` + `content_type_for_lane()`：lane→内容类型路由【单一真相源】（homepage=entity/article=article/image=image，未知回落 article）。
- `quwoquan_data/scripts/download/handler.py`
  - `expectedContentType` 由 `content_type_for_lane(source.researchLane)` 路由（替代硬编码 `"article"`）。
  - source_plan stage result 增 `dispatchByContentType`（按内容类型分桶计数），显式记录分类型下发调度，便于审计/续跑。
- 测试：`test_three_class_decouple` 增 `content_type_for_lane` 路由契约（三类不串味 + legacy 回落）。

## 剩余（P3 后续）

- 实体多源「择优」更细的跨百科打分（当前主源资格已收敛到百科类，择优排序随 P7 放量验证 / P3c）。
