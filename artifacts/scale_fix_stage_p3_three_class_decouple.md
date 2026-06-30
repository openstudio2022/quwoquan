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

### P3-4 实体多源（wiki/百度/搜狗百科）择优一致性

现状（已实现的择优）：
- 多源候选：homepage 发现同时给出 wiki + 百度 + 搜狗百科（auto_plan_writer）。
- 择优取质量最好：`build/homepage._select_homepage_base_draft` 先按 `_homepage_source_priority`（P3a 仅百科 >0）过滤，再按 `factReady → priority → factCount → score → length` 降序取 `best`；`_homepage_plan_sort_key` 中 encyclopedia=bucket 0 优先，`primaryEvidenceRef` 取首个百科。

本批补齐（消除 sourceRole 第二真相源 / 与 P3a 一致）：
- `quwoquan_data/scripts/download/research/auto_plan_writer.py`
  - 新增 `_encyclopedia_role()`：首个被接受的百科作 `primary`，官网与其余百科/补充源一律 `supporting`；wiki/百度/搜狗均改用该 helper（wiki 缺失则百度升 primary，再缺则搜狗），官网固定 supporting。
  - homepage 无种子的 unavailable reason 改为「homepage has no encyclopedia (wiki/baidu/sogou) seed source for baseDraft」。
- `quwoquan_data/scripts/task/run.py`：unrecoverable / replacement 标记的 reason 子串改为稳定前缀 `homepage has no encyclopedia`（nextAction 标记不变）。
- `quwoquan_data/scripts/task/run_download_hints.py`：homepage 修复动作 `add_or_replace_homepage_encyclopedia_seed_source`（去掉 official）。
- 测试同步 P3 策略：
  - `tests/build/test_build_homepage.py`：新增 `_seed_factready_encyclopedia_homepage_source`；`test_prepare_promotes_fact_ready_encyclopedia_over_short_wiki_redirect`（百科被择优）+ `test_prepare_does_not_promote_official_homepage_source`（官网不得 seed）；两个 finalize 测试改用 fact-ready 百科种子。
  - `tests/local_contract/task/test_download_repair_prompt__local_contract_test.py`：断言新 action 名。

## P3 收口

三类物理解耦闭环：
- 实体：来源/seed 主源【只限百科】(wiki/百度/搜狗)，多源择优取质量最好，sourceRole 与消费侧一致。
- 文章：图文混排/长文 + 必须有标题（既有判据）+ 含内联视频则弃稿（P3a）。
- 图片：lane 物理分离 + lane-scoped 抓取/选图（专业图库真实接入见 P4）。
- download：按内容类型路由（`content_type_for_lane`）+ 分类型下发调度（`dispatchByContentType`），去「全部当 article」实体键控默认。

回归：`test_build_homepage`(21) + `test_download_repair_prompt` + `test_source_plan_registry_guidance` + `test_auto_research_article_homepage` + `test_three_class_decouple` 全绿（57 passed）。批量 task 套件 254 passed（1 例 content_supply 为既有 batch 共享态污染，独立运行通过，门禁按文件执行不受影响）。

## 发现：tests/build 测试源被 .gitignore 误伤（既有风险，待用户确认登记 backlog）

- 事项：`quwoquan_data/tests/build/**` 与 `quwoquan_data/tests/local_contract/build/**`（共 5 个测试源：`test_build_homepage.py`、`test_entity_object_stages.py`、`test_build_homepage__local_contract_test.py`、`test_entity_object_stages__local_contract_test.py`、`test_homepage_prepare__local_contract_test.py`）被 `.gitignore:21` 的 `build/` 规则整目录忽略，全部未入库；其中 `test_build_homepage.py`(verify L92)、`test_homepage_prepare__local_contract_test.py`(verify L110) 被门禁脚本引用。另 `test_entity_object_stages.py` 存在既有 `finalize_entity_objects` ImportError（导入 `build.homepage` 不存在符号）。
- 原因：`build/` 宽泛匹配仓库内任意名为 `build` 的目录，连带 `tests/build`、`tests/local_contract/build` 测试源码（非构建产物）。
- 影响：全新检出缺这些文件 → `verify_quwoquan_data.sh` 引用不存在文件；测试修复无法随提交进入版本库。
- 本批处理：本人 P3 直接改写并被门禁直接执行的 `tests/build/test_build_homepage.py` 采用仓库既有机制 `git add -f` 强制入库（与 `scripts/build/**` 同样方式跟踪）。其余 4 个未触及/损坏文件不擅自入库，作为风险上报，待用户确认后统一处理（根因建议：`.gitignore` 增加针对性负向规则恢复 `tests/**/build/` 测试源，并修复 `test_entity_object_stages.py` 的 ImportError）。
