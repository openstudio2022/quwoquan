# 来源矩阵 v2、访问政策闭集与 exact 取证模板

本文件只写领域约束与可重放的查询形状，供任何会话直接复用；不是工具教程，也不允许据此在仓内新增抓取器。所有出网由宿主 AI 用通用工具（`curl`、`yt-dlp`、`html2text`、`jq`、看图）或 [recipes.md](recipes.md) 的临时模板执行；API key 只放本机 shell env（如 `~/.zshenv`），不进仓库。

## 通用约束

- User-Agent 必须声明产品与联系方式，例如 `QuwoquanContentProducer/1.0 (https://quwoquan.example; data-engineering contact) curl`；匿名或通用 UA 会被 Wikimedia 等站点更快限速。
- 同一来源站点串行、≥0.5–1s 间隔、遵守站点 robots 声明的 Crawl-delay（如 `bbs.qyer.com` 为 3s）；遇 429/503 立即停止该站点本轮请求、按候选级放弃剩余候选（原因码 `source_throttled`），不在同一轮反复重试。用合规 UA 实测 Commons 连续 14 个缩略图 + 9 个原件、0.5s 间隔零 429。
- 新增站点前先读 `https://<host>/robots.txt` 与服务条款，把结论记成每条来源行的 `accessPolicy`（下节闭集）；robots/ToS 限制**只记录、不阻断入池**，公众可见性由运营策略决定。唯一仍然禁止的是**技术性规避**：登录墙、付费墙、验证码、DRM、反爬挑战页——这些站点不进入任何自动化路径。
- API 响应先落文件再用 `jq -c` 摘要读取，不把大 JSON 直接读进上下文；工作区布局 `.qwq_output/data/local/workspace/<round>/{round.json,ingest.*.json,api/,sources/,downloads/}` 与 `.qwq_output/data/local/workspace/frontier/{entities,videos,creators}.json`，全部可由本文件与 recipes.md 重建。

## accessPolicy 闭集与权利记录（只记录）

每条来源行可申报 `accessPolicy`：`open`（robots 与条款均允许自动访问）、`robots_disallowed`（robots 对通用 agent 禁止该路径，但页面/CDN 对合规 UA 可达）、`tos_restricted`（服务条款限制自动访问或下载，但内容公开可达）。acquire 原样透传到 `meta.json` 与资产行，release header 汇总 `accessRestrictedAssetIds`；缺席不等于 `open`，缺席就是缺席。

权利派生只看 `license` 文本：白名单（CC0 / CC BY / CC BY-SA / PD 及其版本）→ `verified`；其它可读文本（「图虫用户协议（版权保留）」「Pinterest 服务条款（转载物，原始权利未知）」「Bilibili 用户协议（版权保留）」）→ `unverified` 或 `unknown`，并派生 `authorizationRequired=true` 进入 header 的 `authorizationRequiredAssetIds`。版权保留与权利未知来源**一律入池**，caption 标注作者与来源链接；开不开放由运营配置决定。

## 来源矩阵 v2（综合平台 → 垂类；今日逐站实测）

### 图片

| 层 | 来源 | 访问方式 | 权利 | accessPolicy | 批量路径 |
| --- | --- | --- | --- | --- | --- |
| 综合开放许可 | Wikimedia Commons | API + 直链，`sha1` 可核 | CC BY/BY-SA/CC0/PD → `verified` | `open` | 高产上传者 `allimages&aiuser`（Zhangzhugang / Huangdan2060 / Gisling / N509FZ 各 ≥2,500 文件，Fanghong 1,473，Charlie fong 682）；`Category:Quality images of China`（180+10 子类）/ `Featured pictures of China`（33）/ `Valued images` 作 S1 |
| 综合开放许可 | Openverse `api.openverse.org` | 无 key，匿名限速 | CC0/BY/BY-SA → `verified`；返回 `creator`/`license`/原站链接 | `open` | 按实体英文名检索，是 Flickr 无 key 的替代入口 |
| 综合开放许可 | Flickr API | 需 `FLICKR_API_KEY`（免费即时） | `license=4,5,9,10` → `verified` | `open` | `people.getPublicPhotos` + `photos.getInfo`（views/faves/comments）；无 key 时网页 robots `Disallow: /`，公共 feed 每次 20 条无互动数 → 不可批量 |
| 综合开放许可 | Unsplash / Pexels / Pixabay API | 需 key | 自有免费许可 → `unverified` | `open` | 只补位 |
| 综合聚合 | Pinterest | 用户/画板 RSS `https://www.pinterest.com/<用户>/feed.rss`、`/<用户>/<画板>.rss`（标题、pin 链接、236px 缩略图）；WebSearch `site:pinterest.com <实体> 摄影`；取图把 `i.pinimg.com/236x/<hash>.jpg` 改写为 `/originals/<hash>.jpg`（实测 200） | 转载物、原始权利未知 → `unknown` + `authorizationRequired`；`creator` 写画板主人与画板名，原作者未标注时如实写「pin 转载，原作者未标注」 | `robots_disallowed`（i.pinimg.com 对通用 agent `Disallow: /`） | 画板 RSS；官方 API v5 standard access 作可选升级；视频 pin 多为二传短视频，不作视频来源 |
| 垂类摄影 | 图虫 `tuchong.com` | `https://tuchong.com/rest/tags/<标签>/posts?page=&count=20&order=weekly` 与 `/rest/sites/<site_id>/posts` 对合规 UA 返 JSON；CDN `https://photo.tuchong.com/<user_id>/f/<img_id>.jpg` 无防盗链 | 版权保留 → `unverified` + `authorizationRequired`；`license` 写「图虫用户协议（版权保留）」 | `tos_restricted`（robots 只禁 `/admin/` 与 `/api/`，`/rest/` 不在其中） | 按标签周榜与摄影师批量；每图博带 `favorites/comments/views/shares/collected/rewards`、作者 `site_id`、图片 `img_id/user_id/width/height`（实测 4880×3660） |
| 垂类摄影 | 500px / LOFTER / 蜂鸟 / 色影无忌 / POCO / 米拍 | 500px 纯脚本应用接口私有 → 只作发现；LOFTER `/post/` robots 禁、可按 `accessPolicy` 记录但优先级低；蜂鸟 403、POCO/米拍不可达 → 技术性 ✗；色影无忌全站禁且论坛帖图参差 → 暂不接 | — | — | — |
| 自然户外 | iNaturalist API | 无 key；`quality_grade=research&photo_license=cc0,cc-by,cc-by-sa`，中国境内 43,189 条 | → `verified` | `open` | 自然保护区/观鸟观兽实体的图片作品，带地点与物种 |
| 自然户外 | Mapillary | token 免费 | CC BY-SA | `open` | 只作到达/街景配图 |
| 历史影像 | archive.org / Europeana / 美国国会图书馆 | API/直链 | 公有领域 | `open` | homepage「历史」段配图，量小 |

### 视频

| 层 | 来源 | 访问方式 | 权利 | accessPolicy | 批量路径 |
| --- | --- | --- | --- | --- | --- |
| 开放许可 | Wikimedia Commons | `generator=search&gsrnamespace=6&gsrsearch=<地名> filetype:video`，imageinfo 带 `size/duration` | → `verified` | `open` | 771 条中国相关候选作底；`size > 512 MiB` 不下载 |
| 开放许可 | YouTube（yt-dlp 无 key） | 发现 `yt-dlp --flat-playlist -J "ytsearch8:<实体> 航拍 4K"`；频道批量 `yt-dlp --flat-playlist -J https://www.youtube.com/@<频道>/videos`；单条 `yt-dlp -J <watch>` 给 `license`（"Creative Commons Attribution license (reuse allowed)"）、`view_count/like_count/comment_count/channel_follower_count` | 只下载 `license` 含 `Creative Commons` 的 → `verified`（CC BY 3.0）；`rightsIssues` 注明平台 ToS 对下载的限制 | `tos_restricted` | 频道 `/videos` 批量；Data API v3 key 到位即换官方 `videoLicense=creativeCommon` 发现 |
| 开放许可 | archive.org / Vimeo（`filter=CC-BY`，需 token）/ mixkit / coverr | API | CC/PD 或自有许可 | `open` | 量小，补位 |
| 版权保留 | Bilibili（yt-dlp） | 直连接口对合规 UA 返 412；`yt-dlp -J <BV>` 稳定给出标题/UP 主/播放/点赞/评论/时长；`yt-dlp --flat-playlist -J https://space.bilibili.com/<mid>/video` 与 `bilisearch:` 拿 UP 主全部视频 ID | 版权保留 → `unverified` + `authorizationRequired` | `tos_restricted` | 旅行航拍 UP 主批量（单人常有数百条），视频放量主力之一 |
| 版权保留 | Dailymotion API | 无 key；`views_total/likes_total/owner` | → `unverified` | `tos_restricted` | 中文旅行内容有但杂 |
| ✗ | 抖音 / 快手 / 西瓜 / 小红书 | 登录墙（技术性规避） | — | — | 不进入 |

### 文章与事实参考（全部 `factual_reference_only`，正文由 author 亲笔）

| 层 | 来源 | 访问方式 | accessPolicy | 说明 |
| --- | --- | --- | --- | --- |
| 综合百科 | zh.wikipedia / zh.wikivoyage / 头条百科 `www.baike.com` | API / 页内结构化 JSON | `open` | homepage 必须至少一个百科 `page` 来源；头条百科是秘境级实体的主补位 |
| 新闻旅游频道 | 新华网 `news.cn`、中国新闻网 `chinanews.com.cn` | robots 全开，服务端渲染 | `open` | 节庆、开放、交通等热点事实，补 `practical_density` |
| 政府与官方 | `gov.cn`、各省市文旅厅、景区官网 | 多为默认允许 | `open` | 门票/开放时间/季节的权威事实源 |
| 旅行 UGC | 携程 `you.ctrip.com/sight/**`（景点榜：热度分/评分/点评数/标签）与 `/travels/**`（游记，SSR） | robots 允许 | `open` | 游记作者页非 SSR，作者批量不可得，按目的地列表取 |
| 旅行 UGC | 磨房 `doyouhike.net` | robots `Allow: /`，首页 SSR | `open` | 户外/徒步/秘境线路帖；帖子页可达性待抽验 |
| 旅行 UGC | 马蜂窝 | robots 全站禁；若页面 SSR 可按 `accessPolicy=robots_disallowed` 取事实参考 | `robots_disallowed` | 待抽验 |
| ✗ | 美篇（搜索 SPA）、十六番、途牛、大众点评、穷游（503）、去哪儿（挑战页）、知乎、微信公众号 | SPA / 503 / 反爬 / 登录墙 | — | 技术性规避，不进入 |

## 创作者优先的批量路径

发现 → 定位创作者 → 批量拉全部作品 → 候选级筛选（许可、尺寸、时长、主体） → AI 按文件名/类目/标题归到实体 → 进入轮次 ingest 并记录 `discoverySignals`。exact 模板见 recipes.md `creator_bulk.py`；四条主路径：

- Commons 上传者：`list=allimages&aiuser=<user>&ailimit=500&aiprop=url|sha1|size|mime|timestamp|extmetadata` 逐页（`aicontinue`），文件名系统含地名（如 `Anshun Longgong 20250815`）；结构化 `depicts` 未填充，实体归属由 AI 判定。
- YouTube 频道：`yt-dlp --flat-playlist -J https://www.youtube.com/@<频道>/videos`（标题/时长/观看数）→ 逐条 `yt-dlp -J` 取 `license` 与互动 → 只下载 CC。
- Bilibili UP 主：`yt-dlp --flat-playlist -J https://space.bilibili.com/<mid>/video` → 逐条 `-J` 取播放/点赞/评论 → `unverified` 入池。
- 图虫标签/摄影师：`/rest/tags/<标签>/posts?order=weekly` 与 `/rest/sites/<site_id>/posts`，每图博多图，直接带互动指标。

产物 `frontier/creators.json`（统一行结构见 recipes.md）与 `frontier/creator_entity_map.json`（AI 写的「文件名前缀 → 实体名」映射）。每轮先从创作者批量结果里挑「素材充足的实体」再补百科，反转 r03 的「先定实体再找图」。

## 来源与创作者分层、互动维度（只记录、只排序，不做门）

- `sourceTier`：S1 = Commons QI/FP/VI、YouTube 频道订阅 ≥5 万且该视频 views ≥1 万、Flickr Explore 或 faves ≥ 该作者中位数 2 倍；S2 = 高产可信创作者的普通作品（Commons 上传 ≥500 且有 QI、YouTube CC 频道 ≥50 条上传、Flickr Pro）；S3 = 其它开放许可单品；S4 = 非白名单许可（`unverified`/`unknown`：图虫、Pinterest、Bilibili、Dailymotion）。
- `creatorTier`：C1 = S1 作品 ≥10 件；C2 = 累计 ≥200 件切题作品；C3 = 其余。创作者以 `creator` 字段 + `discoverySignals.creatorFollowers/creatorWorks` 记录，`creatorId` 写进 ingest 行的 `creator` 文本（脚本不解析）。
- 互动维度写进 `discoverySignals`（数字，只记录）：`views`、`likes`（Flickr faves / YouTube likes / 图虫 favorites）、`comments`、`favorites`（图虫 collected）、`shares`、`creatorFollowers`、`ageDays`、`sourceTier`（1–4）、`creatorTier`（1–3）；分析期再算比率，不存派生值。评分校准时反推 `sourceTier`/互动量与六维 `qualityScores` 的相关性，修订 [quality.md](quality.md) 锚点与候选阈值。

## 实体前沿（开放式，不设上限）

分层消费，先 `release pool-query` 做集合差再 init：

- T1 `Category:国家5A级旅游景区`（357 条）；T2 `Category:国家4A级旅游景区` 31 个省子类（约 1,450 条）；T3 `Category:国家一级博物馆`（31 省子类，240 条）、`Category:中国历史文化名镇`（307）、`Category:中国历史文化名村`（157）、`Category:中国国家级自然保护区`（195）；T4 `Category:国家3A级旅游景区`（81）与各省 A 级旅游景区列表页（湖南/安徽/辽宁/吉林/青岛等）；T5 秘境与网红地：AI 按地域给名单（川西：党岭、莫斯卡、格聂、措普沟、冷嘎措、孟屯河谷、稻城亚丁外围；新疆：独库公路节点、赛里木湖、喀纳斯外围、帕米尔；西藏：阿里、然乌湖、丙察察；云南：雨崩、丙中洛、诺邓）+ 携程景点榜类型筛选；T6 `Category:<省>境内的全国重点文物保护单位`（山西 565、四川 357、河北 307、浙江 246…，剔 `全国重点文物保护单位小作品`），按 intro 厚度筛。
- 携程景点榜是热点与非 A 级实体的主发现面：`https://you.ctrip.com/sight/<城市拼音+id>/s0-p<N>.html`（如 `chengdu104`），服务端渲染，可见文本里每个 POI 依次给出名称、等级、「2026中国100必打卡景点」等标签、热度分（如 9.2）、评分（4.7/5）、点评数（5.7万条点评）、距市中心距离与门票；筛选参数在页面里以类型词呈现（自然风光、户外活动、名胜古迹、温泉泡汤、夜游观景、玩水避暑）。落盘后用 `python3 -c` 一行正则抽 `名称/等级/热度/点评数`，只作排序与 `discoverySignals`。
- 热度代理：携程热度分与点评数（`ctripHeat`/`ctripReviews`）、维基 pageviews（`wikiViews30d`）、Flickr `interestingness`/faves（`flickrFaves`）、YouTube `viewCount`（`ytViews`）。只作候选排序与记录，不作门。

## 候选级质量筛选（可重放，不合格换候选、不落台账）

- homepage：百科正文 ≥ 600 字且有信息框或 ≥3 条结构化事实；非消歧义；名称能定位到行政区；0 张可用配图走 text_only。
- article 事实参考：游记正文 ≥ 1,500 字；含具体行程/交通/费用/时间/贴士 ≥3 项；发布 ≤ 3 年；非软广（推广词、店铺链接密度）；非纯图流水账；单篇不够多篇合参。
- image：长边 ≥ 1,600px；非扫描件/图表/地图/截图；主体切题（看原件）；水印为 `platform_logo|stock_agency` 排除；曝光/构图基本合格。长宽比 ≤ 3:1 优先作 image 载体作品；更宽的全景接片（4:1–12:1）可入池但更适合作 homepage/article 配图，image 载体每实体至多 1 张全景。
- video：时长 15s–5min；≥720p；实景为主；无二传平台烫印；能落到已发布或同轮实体。

## 试轮沉淀的候选级判据（可重放）

- Commons `LicenseUrl` 常为 `http://`，写 ingest 前统一改 `https://`，否则整份清单被 schema 拒绝。
- 视频候选先按 imageinfo 的 `size` 过滤：超过 `sourceAssetMaxBytes`（512 MiB）的源体 ingest 必拒，不要下载；4K 航拍原件常达 500 MB–1 GB。
- 说明文字或作者含「中新视频 / China News Service」等新闻机构二传的视频，画面几乎必带平台烫印，按 `platform_logo` 候选级排除；看 poster 前无法确认时，ingest 申报 `unknown`，由 author/reviewer 看 poster 后决定退轮。
- 巨幅全景接片按 `media_processing.policy.yaml` 的 `maxSourcePixels`（6 亿像素）判可读，派生用 JPEG draft 低内存解码；像素超 `maxPublishableImagePixels`（8,000 万）的源在下载截面自动降采样到 `full` 档入池，不再需要按 ≤ 50 MP 挑原件。仍超 6 亿像素或 imageinfo `size` 超 512 MiB 的候选级放弃，不下载。
- 下载后 `sha1` 与 imageinfo 不符（文件页被覆盖上传）按 `source_sha1_drift` 候选级换图，不重试。
- 条目自身配图里常混有位置图、地形图、旗徽、老照片、博物馆建筑照与「同名不同地」的图（如城墙条目里的他处遗址），image 载体必须看原件确认主体就是该实体。
- 头条百科头图 `License` 为空、`Copyright` 为 `no_copyright`/空时不能作资产，只能 text_only 或另取 Commons 图。
- Commons 高产上传者按时间倒序的最近 1,000 张多为县级文保、城市建筑与海外生活照（广丰宗祠、长沙楼盘、多伦多商场），旅游实体命中率低；更高效的批量入口是 `Category:Quality images of China`（180）、`Featured pictures of China`（33）与 `Quality images of Yunnan`（107）——省级 QI 子类多数不存在，先 `categorymembers` 探一次再拉。QI/FP 行记 `sourceTier=1`。
- 图虫 CDN `https://photo.tuchong.com/<user_id>/f/<img_id>.jpg` 对未登录访问只给**长边 1200px** 的压缩版（rest 元数据里的 `width/height` 是原图尺寸，不是可下载尺寸），`/l/`、`/m/` 路径 404；因此图虫图只能作 homepage 封面与 article 配图，**不进 image 载体**（长边 <1,600 不达标）。Commons 直链现在带 `?utm_source=...` 查询串，写 `directUrl` 与拼缩略图前必须 `split("?")[0]`；Commons 缩略图只接受固定宽度档（500/1280/1920 等，640/800/1000 返回 400），预览拼图用 `500px-`。
- 图虫 `/rest/tags/<标签>/posts` 连续约 12 次请求后开始返回 HTML 挑战页（`Expecting value`），按 `source_throttled` 停止本轮该站请求；每轮最多 3–4 个标签、每标签 3 页、间隔 ≥3 s；`siteList` 是以 `site_id` 为键的对象，作者名从这里取，`weekly` 为空时退到 `order=new`。
- Bilibili `space.bilibili.com/<mid>/video` 列表经常 412/352（风控），只能偶发拿到部分 BV 号；稳定路径是 `bilisearch:` 发现 + 单条 `-J`（每条约 3 s，间隔 1.5 s，遇 412 等 12 s）。单条元数据稳定给出播放/点赞/评论/时长/`filesize_approx`。
- YouTube Creative Commons 过滤可以直接在检索 URL 上做：`https://www.youtube.com/results?search_query=<词>&sp=EgIwAQ%253D%253D` 交给 `yt-dlp --flat-playlist -J`，单次返回 30–400 条 CC 视频；中文地名 + 「航拍 4K」14 组查询得 2,004 条候选，剔除新闻机构（中国新闻社/大纪元）后逐条 `-J` 确认 `license` 与互动指标（100% 为 CC）。
- Openverse 匿名配额极小（几次后即 401/429），实际使用需免费注册 API key（`OPENVERSE_CLIENT_ID/SECRET`）；无 key 时不列为可用来源。Pinterest 画板 `.rss` 对多数用户/画板返回 404，搜索页为纯前端应用无 pin 数据；只能对已知有 RSS 的用户用 `/<用户>/feed.rss`，其余靠 WebSearch 发现。

## exact 模板

维基条目筛厚度（批 20，intro 长度作厚度代理）：

```text
https://zh.wikipedia.org/w/api.php?action=query&format=json&prop=extracts|pageprops&exintro=1&explaintext=1&exlimit=20&redirects=1&variant=zh-cn&ppprop=wikibase_item|disambiguation&titles=<T1>|<T2>|...
```

维基类目成员（含分页 `cmcontinue`）：

```text
https://zh.wikipedia.org/w/api.php?action=query&format=json&list=categorymembers&cmtitle=Category:<类目>&cmtype=page&cmlimit=500
```

维基单页全文（`source.md` 正文）与信息框 wikitext（`source.md` 信息区原文），单页一请求：

```text
https://zh.wikipedia.org/w/api.php?action=query&format=json&prop=extracts|info&explaintext=1&redirects=1&variant=zh-cn&inprop=url&titles=<名>
https://zh.wikipedia.org/w/api.php?action=parse&format=json&page=<名>&prop=wikitext&section=0
```

`source.md` 拼装：`# <标题>` + 空行 + extract 正文 + `## 信息区（原文）` + section 0 wikitext 中的 `{{Infobox ...}}` 块 + `## 信息区取证`（AI 亲笔，逐条「字段：取值」）+ `- 来源条目：zh.wikipedia「<标题>」revid <lastrevid>`。

维基条目自身配图 → Commons 元数据（过滤 svg/gif/png 图标；`iiurlwidth` 只用于预览，下载仍取原件以核 `sha1`）：

```text
https://zh.wikipedia.org/w/api.php?action=query&format=json&prop=images&imlimit=50&titles=<名1>|<名2>|...
https://commons.wikimedia.org/w/api.php?action=query&format=json&prop=imageinfo&iiprop=url|sha1|size|mime|extmetadata&iiextmetadatafilter=LicenseShortName|LicenseUrl|Artist|ImageDescription|Credit&titles=File:<A>|File:<B>|...
```

Commons 类目文件与视频检索：

```text
https://commons.wikimedia.org/w/api.php?action=query&format=json&generator=categorymembers&gcmtitle=Category:<类目>&gcmtype=file&gcmlimit=50&prop=imageinfo&iiprop=url|sha1|size|mime|extmetadata
https://commons.wikimedia.org/w/api.php?action=query&format=json&generator=search&gsrnamespace=6&gsrsearch=<地名> filetype:video&gsrlimit=30&prop=imageinfo&iiprop=url|sha1|size|mime|extmetadata
```

头条百科条目页（URL 编码名称；正文与 Infobox 在最大的一段 `<script>` JSON 里，图片行带 `license`/`copyright`）：

```text
https://www.baike.com/wiki/<URL 编码名称>
```

落盘：`curl -sS -A "$UA" <url> -o api/<名>.html`，再用 `python3 -c` 一行取最大 `<script>` 块、`json.loads` 后递归收集 `text` 字段拼成正文、收集 `Infobox` 项拼成信息区，写成与维基同形的 `source.md`；条目不存在时页面标题不含该名称，按候选级放弃。

携程游记检索与正文落盘（`html2text` 去标签，`factual_reference_only`）：

```text
WebSearch：site:you.ctrip.com/travels <实体名> 游记 OR 攻略
curl -sS -L -A "$UA" <游记 URL> | html2text --ignore-images --ignore-links > sources/<slug>.ctrip.source.md
```

维基 pageviews（月度，作 `wikiViews30d`）：

```text
https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/zh.wikipedia/all-access/user/<URL 编码名>/monthly/<YYYYMM01>00/<YYYYMMDD>00
```

Flickr（`FLICKR_API_KEY`；许可 4=BY 5=BY-SA 9=CC0 10=PDM；`url_o` 原件、`url_l` 1024 预览；`getInfo` 取 license 原文与 owner 署名）：

```text
https://api.flickr.com/services/rest/?method=flickr.photos.search&api_key=$FLICKR_API_KEY&text=<实体名 或 英文名>&license=4,5,9,10&sort=interestingness-desc&content_type=1&media=photos&extras=license,owner_name,url_o,url_l,o_dims,views&per_page=30&format=json&nojsoncallback=1
https://api.flickr.com/services/rest/?method=flickr.photos.getInfo&api_key=$FLICKR_API_KEY&photo_id=<id>&format=json&nojsoncallback=1
```

`sourceUrl` 写 `https://www.flickr.com/photos/<owner>/<id>/`，`directUrl` 写 `url_o`，`license` 写 `CC BY 2.0` 等原文，`licenseUrl` 写对应 creativecommons 地址，`creator` 写 `owner_name`。

YouTube Data API（`YOUTUBE_API_KEY`；发现只走官方接口，下载走 `yt-dlp`）：

```text
https://www.googleapis.com/youtube/v3/search?key=$YOUTUBE_API_KEY&part=snippet&type=video&videoLicense=creativeCommon&videoDuration=short&order=viewCount&maxResults=25&q=<实体|地区> 航拍 OR drone OR 4K
https://www.googleapis.com/youtube/v3/videos?key=$YOUTUBE_API_KEY&part=snippet,contentDetails,statistics,status&id=<id1>,<id2>
yt-dlp -f "bv*[height<=720][ext=mp4]+ba[ext=m4a]/b[height<=720]" --merge-output-format mp4 -o downloads/<slug>.mp4 https://www.youtube.com/watch?v=<id>
```

`status.license` 必须为 `creativeCommon`；`sourceUrl` 写 watch 地址，`directUrl` 写同一地址，`license` 写 `CC BY 3.0`，`licenseUrl` 写 `https://creativecommons.org/licenses/by/3.0/`，`creator` 写频道名，`hasAudio` 按实际，`rightsIssues` 由脚本按白名单派生 `verified`；`discoverySignals.views` 记 `viewCount`。

YouTube / Bilibili 无 key（yt-dlp；发现、批量、单条元数据、下载）：

```text
yt-dlp --flat-playlist -J --user-agent "$UA" "ytsearch8:<实体> 航拍 4K"
yt-dlp --flat-playlist -J --user-agent "$UA" https://www.youtube.com/@<频道>/videos
yt-dlp -J --user-agent "$UA" https://www.youtube.com/watch?v=<id>          # .license / .view_count / .like_count / .comment_count / .channel_follower_count / .filesize_approx
yt-dlp --flat-playlist -J --user-agent "$UA" https://space.bilibili.com/<mid>/video
yt-dlp -J --user-agent "$UA" https://www.bilibili.com/video/<BV>            # .title / .uploader / .view_count / .like_count / .comment_count / .duration
yt-dlp -f "bv*[height<=720][ext=mp4]+ba[ext=m4a]/b[height<=720]" --merge-output-format mp4 --user-agent "$UA" -o downloads/<实体>__video__<slug>.mp4 <url>
```

YouTube 只下载 `license` 含 `Creative Commons` 的条目；Bilibili 行 `license` 写「Bilibili 用户协议（版权保留）」、`accessPolicy=tos_restricted`；`filesize_approx > 536870912` 候选级放弃。

图虫（rest JSON 对合规 UA 直出；`license` 写「图虫用户协议（版权保留）」、`licenseUrl` 写 `https://tuchong.com/agreement/`、`accessPolicy=tos_restricted`；`sourceUrl` 写图博页 `https://tuchong.com/<site_id>/<post_id>/`，`directUrl` 写 CDN 原图，`creator` 写摄影师名 + 主页）：

```text
https://tuchong.com/rest/tags/<URL 编码标签>/posts?page=1&count=20&order=weekly
https://tuchong.com/rest/sites/<site_id>/posts?page=1&count=20
https://photo.tuchong.com/<user_id>/f/<img_id>.jpg
```

Pinterest（RSS 发现 + originals 取图；`license` 写「Pinterest 服务条款（转载物，原始权利未知）」、`accessPolicy=robots_disallowed`；`sourceUrl` 写 pin 页，`directUrl` 写 originals，`creator` 写「<画板主人>/<画板名>（pin 转载，原作者未标注）」）：

```text
https://www.pinterest.com/<用户>/feed.rss
https://www.pinterest.com/<用户>/<画板>.rss
https://i.pinimg.com/236x/<hash>.jpg  →  https://i.pinimg.com/originals/<hash>.jpg
```

Openverse（无 key；`license=cc0,by,by-sa`）与 iNaturalist（无 key；`quality_grade=research&photo_license=cc0,cc-by,cc-by-sa`；照片 URL 把 `square` 换 `original`）：

```text
https://api.openverse.org/v1/images/?q=<实体英文名>&license=cc0,by,by-sa&page_size=50&page=1
https://api.inaturalist.org/v1/observations?place_id=<地点 id>&quality_grade=research&photo_license=cc0,cc-by,cc-by-sa&photos=true&per_page=100&order_by=votes
```

下载循环（同站串行）：

```text
UA="QuwoquanContentProducer/1.0 (https://quwoquan.example; data-engineering contact) curl"
while read -r url out; do curl -sS -L -A "$UA" --max-time 300 -o "downloads/$out" "$url" -w "$out %{http_code} %{size_download}\n"; sleep 1; done < downloads.txt
```

`jq` 从 imageinfo JSON 生成 ingest 来源行（避免手抄 sha1；`filePath`/`relevance`/水印三字段仍由 AI 补）：

```text
jq -c '.query.pages[] | .imageinfo[0] as $i | {kind:"image", sourceUrl:("https://commons.wikimedia.org/wiki/"+(.title|gsub(" ";"_"))), directUrl:($i.url|split("?")[0]), sha1:$i.sha1, license:$i.extmetadata.LicenseShortName.value, licenseUrl:$i.extmetadata.LicenseUrl.value, creator:($i.extmetadata.Artist.value|gsub("<[^>]+>";"")), description:($i.extmetadata.ImageDescription.value|gsub("<[^>]+>";"")|.[0:200])}' api/<批>.imageinfo.json
```

`jq` 从 `pool-query --json` 构造 cohort（见 [handoff.md](handoff.md)）。
