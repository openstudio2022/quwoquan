# Scale Fix Stage · 新测试接入 verify_quwoquan_data.sh(门禁接线·第一批)

`verify_quwoquan_data.sh` 是**精选清单**门禁(非全量收集),新增测试必须显式接入才会被守护。

## 本步接入(已存在的新/改测试)

在 `verify_quwoquan_data.sh` 末尾(`echo PASSED` 前)新增一个 pytest 块:

- `env/test_cursor_probe`:P0 探针分类(startupTimeout 不计 true5xx + warm 复用)。
- `task/test_cursor_credentials`:key 经 QWQ_CURSOR_API_KEY_FILE 单一真相源。
- `task/test_scaled_e2e_run`:无人托管 scaled-e2e 按 cycles 续跑/重试。
- `common/test_adaptive_word_gate`:RC6 形态自适应字数门(200/600)。
- `common/test_entity_focus`:实体聚焦(is_multi_location_route 死代码已清)。
- `download/test_source_quality_gate`:RC4 候选门红线 + 主页源复用(新布局)。
- `download/test_image_collection_gate`:文章/图片 lane 许可不对称 + UGC text-only。
- `download/test_source_plan_registry_guidance`:源计划注册表指导(死参移除后签名)。
- `download/test_auto_research_{article_homepage,image_lane,transport}`:并行可用性 + 三类来源。
- `produce/test_route_assets_layout`:RC4 文章 1:1 同源资产选取。

## 验证

```
pytest <上述 12 文件> => 91 passed in 46s
```

三个真实可靠性测试(cursor_probe/cursor_credentials/scaled_e2e_run)hermetic、0.66s,
不发真实网络、不挂起,适合常驻门禁。

## 待补(后续子步,能力落地后接入)

- 三类解耦路由契约测试(fix-3class-routing 落地后)。
- 图库适配器测试(Unsplash/Pexels/Pixabay/Wikimedia,fix-image-gallery-sources 落地后)。
- 多语言翻译阶段测试(fix-translation 落地后)。
