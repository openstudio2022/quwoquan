# Scale Fix Stage · RC2/RC4 收尾(同源忠实硬门 + 死代码清理)

阶段:底稿忠实重构 · 离线可验证子步(不依赖真实 Cursor agent 调用)
HEAD 基线:`bec517cb3`(P0 探针修正、RC6 形态自适应字数门)

## 本步改动(生产代码)

1. **RC4 候选门红线** `download/research/source_quality.py::_candidate_gate`
   - `lane == "article"` 且 `imageEvidenceMode == "same_authorized_collection"` → 显式拒绝。
   - 语义:文章配图必须**同源**(来自文章底稿自身图片)。`same_authorized_collection`=用「另一授权图集」的图当文章配图=跨源替代,是九寨沟问题根因之一。
   - **生产零误伤**:全仓库生产代码从不设置 `same_authorized_collection`(`grep` 证实只产出 `same_source` / `""` / `source_unit_assets`);该红线仅封死测试可构造的后门模式,并为未来防回归。

2. **RC4 route_assets 空 baseSourceRef 回退收口** `produce/route_assets.py::_build_route_assets`
   - 删除 `not base_source_ref` 逃逸分支:`baseSourceRef` 缺失时**绝不**回退到借用同实体/兄弟来源的图。
   - 无 `baseSourceRef` ⇒ 不配图(text_only 文章),杜绝九寨沟「跨源替代图」复现。
   - 文章配图 100% 来自 `baseSourceRef` 指向的单一底稿来源 `assets/`。

3. **RC1/RC2 死代码清理** `_common/entity_focus.py`
   - 删除 `is_multi_location_route()` 函数与 `ROUTE_MIN_LOCATIONS` 常量(仅旧「多地点 route」模型使用,1:1 底稿中心下已无引用)。
   - `coverage_targets_mentioned` docstring 更新为 1:1 底稿 + 多标签口径。

## 本步改动(测试,随同源硬门同步到新语义)

- `test_source_quality_gate`:`test_article_base_accepts_ugc_and_platform_article_source_classes_equally` 桩 `same_authorized_collection` → `same_source`(本意测「源类别平等接纳」,与图片证据模式无关)。
- `test_image_collection_gate`:
  - `test_article_candidate_warns_on_bad_optional_image_but_image_lane_blocks_it` 桩 → `same_source`(模拟底稿自身含许可不达标图:文章 lane 仅告警可降级,image lane 硬阻断——保留该不对称断言)。
  - `test_qunar_travelogue_sources_require_entity_route_and_authorized_image` 断言对齐生产现状 `imageEvidenceMode == ""`(RC4:UGC 游记是 text-only 底稿,即便传入 authorized_images 也绝不带替代图)。
- `test_auto_research_article_homepage`:两处 `fake_qunar` 桩 `same_authorized_collection` → `same_source`。
- `test_route_assets_layout`:`_build()` 迁移到 **1:1 单源模型**(carrier=article + baseSourceRef 锚定单一来源,routeNodes 单实体);删除跨实体 `>=3 node` 旧聚合断言,改为 cover/node/closing 三职责 + 同源去重互异;`test_cross_entity_dedup_*` 更名 `test_same_source_assets_perceptually_distinct`。
- `test_source_unit_evidence_chain::test_route_assets_to_post_assets_traceable`:迁移到 1:1 单源(baseSourceRef + 单实体 routeNodes),证据链断言不变。
- local_contract 镜像为自动生成桥接(`generate_canonical_test_bridges.py`, DO NOT EDIT),随基测试自动生效。

## 验证证据(local_contract)

```
pytest -k "qunar_travelogue_sources_require_entity_route or article_candidate_warns or \
  article_base_accepts or parallel_auto_research or museum_article_categories or \
  route_assets or source_unit_evidence_chain or entity_focus"
=> 35 passed
```

stash 基线对照(stash 我的 4 文件后重跑)确认:`parallel_auto_research` / `museum_article_categories` / `route_assets_layout` / `article_candidate_warns` / `article_base_accepts` 由本步改动打破并已修复;`entity_focus` 死代码移除自洽。

## 既有失败(非本步引入,记为 finding,留后续独立子步)

- `test_source_quality_gate::test_verified_homepage_reuse_filters_bad_or_thin_source_units`:
  HEAD `bec517cb3` 即失败(stash 我全部改动后仍失败)——`_verified_homepage_sources_from_source_units` 复用过滤把 `home_official` 也过滤为空。与 RC2/RC4 无关,属「百科主页源复用过滤」回归,待独立子步排查。

## 下一子步(RC4 死参,独立提交)

- 移除 `authorized_images` 死参:`wiki_media.py::_qunar_travelogue_sources` 签名、`auto_plan_facade.py`、`auto_plan_writer.py` 调用点 + ~10 处测试桩签名;同时把 `test_qunar_travelogue_sources_*` 误导性命名(含 authorized_image)一并更正。
