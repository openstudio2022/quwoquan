# 四川景区精选（最新运行记录）

- taskId: `旅行/地域/四川省/景区/景区精选`
- archetype: `region_category_coverage`
- latestBatch: `e2e_sichuan_20260607`
- latestStatus: `download -> build -> produce -> publish 全链路通过`

## 覆盖种子实体

- `地点/景区/峨眉山`
- `地点/景区/乐山大佛`

## 最新落盘位置

- 任务根：`quwoquan_data/runtime/tasks/旅行/地域/四川省/景区/景区精选/`
- 批次根：`quwoquan_data/runtime/tasks/旅行/地域/四川省/景区/景区精选/batches/e2e_sichuan_20260607/`
- 文章成品：
  - `posts/article/环线攻略/峨眉山·攻略/1/article.md`
  - `posts/article/环线攻略/乐山大佛·攻略/1/article.md`
- 草稿与审校：
  - `4.draft/draft.article.md`
  - `4.draft/draft_meta.json`
  - `5.review/`
- 过程来源：
  - `entities/地点/景区/峨眉山/1.download/sources/*`
  - `entities/地点/景区/乐山大佛/1.download/sources/*`

## 质量门结果

- `review`：2/2 approved
- `materialize`：2/2 approved post package
- 图片门：峨眉山/乐山大佛均通过可用性检查，保留为需要人审提示但未阻断交付
- 事实门：门票、开放时间、到达方式已自然融入正文，不再只以清单块出现

## 经验沉淀

- 外层任务目录不承载单批过程证据，批次与对象目录才是实证落点。
- `content_object_index.json` 必须先写，后续 `draft.article.md` 和 `article.md` 才能被唯一定位。
- `generator=agent`、`draft_meta.citedSourcePaths`、`manifest.citedSourceRefs` 必须闭环，否则 review 不能过。
- 商用内容必须把事实、体验、取舍判断、图片安全四件事一起过门，不能只看字数。
