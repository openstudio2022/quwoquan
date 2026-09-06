# 四载体差异

共用六步；本文件只写差异。每个对象只有一份主来源（来源单一类型判定），可附同源配图。

## homepage（实体主页）

- 对象根 `entities/<域>/<类型>/<名称>/`，坐标即实体身份，无 angle/title/seq。
- acquire：一个 zh.wikipedia 条目页；可附该条目 Commons 配图。
- author：`4.draft/page.md`，首行 H1 为实体名，正文含地点、类型、看点、到达方式等事实段；不写 `entity_page_input.json`。
- publish：物化 `_entity.json + page.md + manifest.json`，实体绑定 `entityRef + tagRefs`。

## article（文章）

- 对象根 `posts/article/<angle>/<title>/<seq>/`。
- acquire：一个 zh.wikipedia 主题条目页（线路、文化、事件、现象），可附同页图片。
- author：`4.draft/draft.article.md`，frontmatter：

```yaml
---
title: ...
tagRefs: [Entity/地点/景区, Topic/旅行/玩法/观光游览]
creatorProfileId: qwq_creator_travel_blogger_001
---
```

正文 Markdown；引用图片用 `![caption](assets/<fileName>)`，只允许本对象 `assets/` 内文件。不写 `writing_pack.json`；无配图即 text_only，有配图即 illustrated，不设配图率门。

## image（图片作品）

- 对象根 `posts/image/<angle>/<title>/<seq>/`。
- acquire：1–N 个 Commons 图片文件页，各一句相关性理由。
- author：`4.draft/image_work.json`：`{"title","caption","assetRefs":["assets/..."],"creatorProfileId"}`；至少一个 assetRef。
- publish：`manifest.json` 无正文，事务要求每个 asset 有 rights 结论。

## video（视频）

- 对象根 `posts/video/<angle>/<title>/<seq>/`。
- acquire：一个 Commons 视频文件页（webm/ogv）；脚本抽 poster 帧并写 `posterAssetRef`。
- author：`4.draft/video_script.json`：`{"title","caption","sourceVideoAssetRef","narrative":[...],"creatorProfileId"}`。
- review：`assetRights` 需同时覆盖 video 与 poster 两条。
- publish：poster identity 冻结进 manifest；不设热度、时长下限或探测字段完整性门。
