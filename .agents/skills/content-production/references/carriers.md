# 四载体差异

共用六步；本文件只写差异。每个对象只有一份主来源（来源单一类型判定），可附同源配图。

## homepage（实体主页）

- 对象根 `entities/<域>/<类型>/<名称>/`，坐标即实体身份，无 angle/title/seq；候选绑定必须带 `region`（现有 `Topic/地理/行政区/<region>` 节点，publish 用它派生 `geoTagRef`）。
- acquire：一个 zh.wikipedia 条目页（必须，publish 的 `_entity.json` 要求百科主源）；可附该条目 Commons 配图。
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

正文 Markdown；引用图片用 `![caption](assets/<fileName>)`，只允许本对象 `assets/` 内文件。不写 `writing_pack.json`；无配图即 text_only，有配图即 illustrated（首图自动成为封面，其余为正文图），配图张数不设下限，0 张、1 张、多张都合法。post 的 `entityType/name` 指向的 homepage 必须已发布或同批发布，否则 release 时 `REFERENCE_MISSING`；选题前先用 `release pool-query` 确认实体是否已存在，已发布的实体不能重复 init。

## image（图片作品）

- 对象根 `posts/image/<angle>/<title>/<seq>/`。
- acquire：1–N 个 Commons 图片文件页，各一句相关性理由。
- author：`4.draft/image_work.json`：`{"title","caption","assetRefs":["assets/..."],"creatorProfileId"}`；至少一个 assetRef。
- publish：`manifest.json` 无正文，每个 asset 的权利字段由 acquire 记录、seal 转录。

## video（视频）

- 对象根 `posts/video/<angle>/<title>/<seq>/`。
- 发现：在 Commons 沿 `Category:Videos from China` 类目树检索，不要用不存在的 `Videos of X`。高产出子类：`Drone videos from China`、`Time-lapse videos from China`、`Walking China`、`Videos from Beijing`、`Videos from Shanghai`、`Videos from Hong Kong`、`Videos from Taiwan`、`Videos of nature of China`；用 `action=query&list=categorymembers&cmtitle=Category:<名>&cmtype=file|subcat` 遍历，再用 `list=search&srnamespace=6&srsearch=<地名> filetype:video` 补全文检索。选片只看切题与可播放，不看文件大小与容器。
- acquire：一个 Commons 视频文件页（webm/ogv/mpg/mp4 皆可）；脚本对超预算或容器不在 `mp4|webm` 的源体统一转码为 H.264 mp4（720p、目标约 16 MiB、硬上限为载体预算 50 MiB），登记 `derivativeBinding`，并从派生体抽 poster 帧写 `posterAssetRef`。
- author：`4.draft/video_script.json`：`{"title","caption","scriptLines":["..."],"creatorProfileId"}`；`sourceVideoAssetRef` 缺省取对象唯一 source video。
- review：`assetRights` 由 seal 自动覆盖 video 与 poster 两条，reviewer 不必手写。
- publish：poster identity 冻结进 manifest；不设热度、时长下限或探测字段完整性门。
