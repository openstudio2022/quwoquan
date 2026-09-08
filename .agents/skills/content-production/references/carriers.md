# 四载体分轨

共用六步；本文件只写差异：来源与发现、候选级质量筛选、采集与处理、产物、评分维度（维度锚点见 [quality.md](quality.md)，来源模板见 [sourcing.md](sourcing.md)）。一个实体默认产 1 homepage + 1 article + 1–2 image [+ video]。

## homepage（实体主页，事实型）

- 对象根 `entities/<域>/<类型>/<名称>/`，坐标即实体身份，无 angle/title/seq；候选绑定必须带 `region`（现有 `Topic/地理/行政区/<region>` 节点，publish 用它派生 `geoTagRef`）。实体口径是用户愿意去的一切地方，类型只取 `Entity/地点/*` 现有叶子。
- 来源与发现：名录 = 携程景点榜（按城市遍历、热度排序、读热度分/点评数/「必打卡」标签、类型筛「自然风光/户外活动/温泉/夜游/名胜古迹」以捞出网红地、露营地、秘境）∪ zh.wikipedia 分层类目（5A/4A/3A、一级博物馆、历史文化名镇名村、国家级自然保护区、各省文保）∪ AI 按地域给的秘境名单。主源：有 zh.wikipedia 条目取维基；否则取头条百科 `www.baike.com/wiki/<名>`（publish 实体 schema 的 `toutiao_baike` 成员）。百度百科 robots 全站禁止，不用。
- 候选级筛选（可重放）：百科正文 ≥ 600 字且有信息框或 ≥3 条结构化事实；非消歧义；名称能定位到行政区；热度信号只作排序；有 ≥1 张可用配图优先，0 张走 text_only。
- acquire：一个百科条目页（必须）；可附条目自身配图 / 头条百科 CC 图 / Flickr CC 图。
- author：`4.draft/page.md`，首行 H1 为实体名，正文含位置、类型、看点、到达方式、季节/贴士等事实段；不写 `entity_page_input.json`。
- publish：物化 `_entity.json + page.md + manifest.json`，实体绑定 `entityRef + tagRefs`。
- 评分维度：`fact_traceability` 事实可溯源、`information_completeness` 信息完整、`structure_clarity` 结构清晰、`practical_value` 实用性、`image_relevance` 配图相关与质量、`source_quality` 来源质量。

## article（文章，叙事/攻略型）

- 对象根 `posts/article/<angle>/<title>/<seq>/`。
- 来源与发现：主源是同一实体条目换 `publishAngle`（人文/攻略/风光/美食/摄影/自驾/徒步）或一个主题条目页；事实参考追加携程游记/攻略（`site:you.ctrip.com/travels <实体> 游记|攻略`，按热度/最新）、zh.wikivoyage、robots 允许的公开博客；选题风向参考 YouTube/Bilibili 热门 vlog 标题与携程「必打卡」标签。马蜂窝、小红书、穷游、去哪儿按合规闭集不用。
- 候选级筛选：游记正文 ≥ 1,500 字、含行程/交通/费用/时间/贴士中 ≥3 项、发布 ≤ 3 年、非软广、非纯图流水账；单篇不够则多篇合参。
- acquire：第三方文本全部 `factual_reference_only`（游记页 HTML→text 落盘）；可附同源或 Flickr/Commons 配图。
- author：`4.draft/draft.article.md`，frontmatter：

```yaml
---
title: ...
tagRefs: [Entity/地点/景区, Topic/旅行/玩法/观光游览]
creatorProfileId: qwq_creator_travel_blogger_001
---
```

正文 Markdown，AI 亲笔原创、只取来源事实不搬运表达；引用图片用 `![caption](assets/<fileName>)`，只允许本对象 `assets/` 内文件。无配图即 text_only，有配图即 illustrated（首图自动成为封面），配图张数不设下限。post 的 `entityType/name` 指向的 homepage 必须已发布或同批发布，否则 release 时 `REFERENCE_MISSING`；选题前先用 `release pool-query` 确认实体是否已存在，已发布的实体不能重复 init。
- 评分维度：`fact_traceability`、`originality` 原创性、`angle_and_title` 角度与标题、`practical_density` 实用信息密度、`readability` 可读性与结构、`image_match` 配图匹配。

## image（图片作品，视觉型）

- 对象根 `posts/image/<angle>/<title>/<seq>/`。
- 来源与发现：Flickr API `photos.search`（`license=4,5,9,10`、`sort=interestingness-desc`、`text=<实体名/英文名>`，`getInfo` 取 license 与署名）为主；Wikimedia Commons（条目图与 Commons 类目，Quality/Featured 优先）；头条百科 `license: CC BY-SA 4.0 / copyright: self` 图；Unsplash/Pexels/Pixabay API 只在 CC 池不足时补（`unverified`）。Pinterest、图虫、500px 不进自动化路径，只能以「人工提供文件」登记。
- 候选级筛选：长边 ≥ 1,600px；非扫描件/图表/地图/截图；主体明确切题（AI 看原件）；水印为 `platform_logo|stock_agency` 排除，`author_signature` 保留并申报；曝光/构图基本合格；interestingness/faves、QI/FP 作排序。
- acquire：1–N 个文件页，各一句相关性理由；Commons 附 `sha1`，其他来源以 sha256 自证；逐张看原件申报水印三字段。
- author：`4.draft/image_work.json`：`{"title","caption","assetRefs":["assets/..."],"creatorProfileId"}`；至少一个 assetRef；caption 写地点/季节/视角/故事。
- publish：`manifest.json` 无正文，每个 asset 的权利字段由 acquire 记录、seal 转录。
- 评分维度：`subject_relevance` 切题与主体、`technical_quality` 技术质量、`composition_aesthetics` 构图与美感、`uniqueness` 独特性、`caption_value` caption 信息价值、`rights_clarity` 权利清晰度。

## video（视频，动态视觉型）

- 对象根 `posts/video/<angle>/<title>/<seq>/`。主题偏好：壮美河山——川西、新疆、西藏、雪山江河湖海、航拍、全国游。
- 来源与发现：Commons（`Category:Drone videos from China`、`Aerial videos from China`、`Time-lapse videos from China`、`Walking China`、`Videos from <地区>` 子树，全文 `<地名> filetype:video`）；YouTube Data API `search.list?videoLicense=creativeCommon&videoDuration=short|medium&order=viewCount|relevance`，`videos.list` 取 `viewCount/likeCount/duration/definition`；旅行摄影博主的其他作品只保留逐条命中，不构造作者全集；Pexels/Pixabay/Vimeo CC 补航拍空镜；Bilibili 只在不足时用（`unverified`）。港澳台条目只用于补视频。抖音、快手、小红书不进任何路径。
- 候选级筛选：时长 15s–5min、≥720p、实景为主（非 talking-head/讲解/幻灯）、无二传平台烫印（抖音/快手 logo → `platform_logo` 排除）、切题且能落到已发布或同轮实体（多实体线路落主实体；OPEN-021 判永不入 cohort 的实体不能作落点）；观看数/点赞只作排序。
- acquire：Commons 直链 `curl`；YouTube 用 `yt-dlp -f "bv*[height<=720][ext=mp4]+ba[ext=m4a]/b[height<=720]"` 直取 720p mp4 让多数片段免转码；脚本对超预算或容器不在 `mp4|webm` 的源体统一转码为 H.264 mp4（720p、目标约 16 MiB、硬上限为载体预算 50 MiB），登记 `derivativeBinding`，并从派生体抽 poster 帧写 `posterAssetRef`；视频 execution 的 `task acquire` 放后台运行。看 poster 申报水印。
- author：`4.draft/video_script.json`：`{"title","caption","scriptLines":["..."],"creatorProfileId"}`；`sourceVideoAssetRef` 缺省取对象唯一 source video；scriptLines 基于来源描述与实体事实。
- review：`assetRights` 由 seal 自动覆盖 video 与 poster 两条，reviewer 不必手写。
- publish：poster identity 冻结进 manifest；不设热度、时长下限或探测字段完整性门。
- 评分维度：`subject_relevance` 切题与实体可辨识、`visual_quality` 画质、`editing_rhythm` 剪辑与节奏、`audio_fit` 音轨适配、`unique_perspective` 独特视角、`rights_clarity` 权利清晰度。
