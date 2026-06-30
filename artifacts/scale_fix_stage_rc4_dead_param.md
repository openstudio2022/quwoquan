# Scale Fix Stage · RC4 删除 authorized_images 死参

承接 `scale_fix_stage_rc2_rc4_cleanup.md` 的「下一子步」。

## 背景(真死参)

`_qunar_travelogue_sources` 的 `authorized_images` 参数自始至终**未被函数体使用**
(`images` 恒为空列表、`image_evidence_mode=""`)。RC4 下 UGC 游记是 text-only 文章底稿,
配图必须同源,绝不接受外部「授权图集」。该参数是历史遗留死参,留着会误导「游记可外挂授权图」。

## 改动

生产(3 处):
- `download/research/wiki_media.py::_qunar_travelogue_sources`:删签名 `authorized_images`,补 RC4 docstring。
- `download/research/auto_plan_facade.py::_qunar_travelogue_sources`:删 param + runtime_bridge 透传。
- `download/research/auto_plan_writer.py`:删调用点 `authorized_images=[]`。

测试桩(随签名收敛,统一对齐新生产签名 `(entity_id, *, entity_aliases=(), limit=4)`):
- `test_auto_research_article_homepage`:两处 `fake_qunar` 签名 + 一处 lambda。
- `test_auto_research_image_lane`:7 处 lambda(两种旧写法统一)。
- `test_image_collection_gate`:删调用 kwarg;测试名 `..._require_entity_route_and_authorized_image`
  更正为 `..._require_entity_route_and_stay_text_only`(去掉误导性 authorized_image)。
- `test_source_plan_registry_guidance`:4 处调用删 `authorized_images=[...]`。

全仓库 `authorized_images` 仅剩注释,无任何代码引用。

## 验证

```
pytest -k "auto_research or image_collection_gate or source_plan_registry or source_quality_gate"
=> 77 passed
```
