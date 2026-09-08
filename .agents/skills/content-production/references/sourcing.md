# 来源矩阵、合规闭集与 exact 取证模板

本文件只写领域约束与可重放的查询形状，供任何会话直接复用；不是工具教程，也不允许据此在仓内新增抓取器。所有出网由宿主 AI 用通用工具（`curl`、`yt-dlp`、`html2text`、`jq`、看图）执行；API key 只放本机 shell env（如 `~/.zshenv`），不进仓库。

## 通用约束

- User-Agent 必须声明产品与联系方式，例如 `QuwoquanContentProducer/1.0 (https://quwoquan.example; data-engineering contact) curl`；匿名或通用 UA 会被 Wikimedia 等站点更快限速。
- 同一来源站点串行、≥0.5–1s 间隔、遵守站点 robots 声明的 Crawl-delay（如 `bbs.qyer.com` 为 3s）；遇 429/503 立即停止该站点本轮请求、按候选级放弃剩余候选（原因码 `source_throttled`），不在同一轮反复重试。用合规 UA 实测 Commons 连续 14 个缩略图 + 9 个原件、0.5s 间隔零 429。
- 新增站点前先读 `https://<host>/robots.txt` 与服务条款：对 `User-agent: *` 为 `Disallow: /` 的站点、需要登录才能读正文的站点、ToS 禁止自动访问的站点，不进入任何自动化路径。
- API 响应先落文件再用 `jq -c` 摘要读取，不把大 JSON 直接读进上下文；工作区布局 `.qwq_output/data/local/workspace/<round>/{round.json,ingest.*.json,api/,sources/,downloads/}`，全部可由本文件模板重建。

## 合规闭集（逐站实测 robots / 可达性 / 许可）

可用：

- `zh.wikipedia.org`（API；CC BY-SA 4.0；实体与主题条目）
- `www.baike.com` 头条百科/快懂百科（robots `Allow: /`；页内结构化 JSON；实体条目，秘境级覆盖；publish 实体 schema 成员 `toutiao_baike`；文本许可按其版权声明页如实记录，图片行带 `license`/`copyright` 字段）
- `commons.wikimedia.org` / `upload.wikimedia.org`（API + 直链；图片与视频，`sha1` 可核）
- `you.ctrip.com/sight/**`（景点榜，热度/评分/点评数/标签，服务端渲染，robots 允许）与 `you.ctrip.com/travels/**`（游记/攻略，服务端渲染，robots 允许；文本只作 `factual_reference_only`）
- `zh.wikivoyage.org`（API；CC BY-SA）
- Flickr 官方 API（`api.flickr.com/services/rest`，需 key；`license=4,5,9,10` 为 CC BY / BY-SA / CC0 / PDM）
- YouTube Data API v3（`www.googleapis.com/youtube/v3`，需 key；`videoLicense=creativeCommon` 发现，`yt-dlp` 取 CC BY 片段；`rightsIssues` 注明平台 ToS 对下载的限制）
- Unsplash / Pexels / Pixabay 官方 API（需 key；自有免费许可 → `unverified`，只补位）
- Vimeo API（CC 筛选）、`api.openverse.org`（CC 聚合，匿名限速）
- Bilibili（robots 允许 watch 页；版权保留 → `unverified`；只在前述不足时用）
- 维基 pageviews API（`wikimedia.org/api/rest_v1/metrics/pageviews/...`，热度代理）

不可用（原因）：

- 马蜂窝 `www.mafengwo.cn`：robots `Disallow: /`
- 小红书 `www.xiaohongshu.com`：robots `Disallow: /` + 登录墙
- Pinterest：robots `Disallow: /` + ToS 禁抓
- 百度百科 `baike.baidu.com`：robots `Disallow: /`
- 图虫 `tuchong.com`：正文纯脚本渲染，数据接口 `/api/` 被 robots 禁止，作品版权保留
- 500px：脚本应用、版权保留、接口私有
- 穷游 `qyer.com`：对非浏览器 UA 返 503
- 去哪儿 `travel.qunar.com`：反爬挑战页
- 抖音、快手：登录墙 + ToS
- 图虫/500px/Pinterest 素材只能以「人工提供文件」路径 ingest（用户手工下载并给出授权证据）。

## 实体前沿（开放式，不设上限）

分层消费，先 `release pool-query` 做集合差再 init：

- T1 `Category:国家5A级旅游景区`（357 条）；T2 `Category:国家4A级旅游景区` 31 个省子类（约 1,450 条）；T3 `Category:国家一级博物馆`（31 省子类，240 条）、`Category:中国历史文化名镇`（307）、`Category:中国历史文化名村`（157）、`Category:中国国家级自然保护区`（195）；T4 `Category:国家3A级旅游景区`（81）与各省 A 级旅游景区列表页（湖南/安徽/辽宁/吉林/青岛等）；T5 秘境与网红地：AI 按地域给名单（川西：党岭、莫斯卡、格聂、措普沟、冷嘎措、孟屯河谷、稻城亚丁外围；新疆：独库公路节点、赛里木湖、喀纳斯外围、帕米尔；西藏：阿里、然乌湖、丙察察；云南：雨崩、丙中洛、诺邓）+ 携程景点榜类型筛选；T6 `Category:<省>境内的全国重点文物保护单位`（山西 565、四川 357、河北 307、浙江 246…，剔 `全国重点文物保护单位小作品`），按 intro 厚度筛。
- 携程景点榜是热点与非 A 级实体的主发现面：`https://you.ctrip.com/sight/<城市拼音+id>/s0-p<N>.html`（如 `chengdu104`），服务端渲染，可见文本里每个 POI 依次给出名称、等级、「2026中国100必打卡景点」等标签、热度分（如 9.2）、评分（4.7/5）、点评数（5.7万条点评）、距市中心距离与门票；筛选参数在页面里以类型词呈现（自然风光、户外活动、名胜古迹、温泉泡汤、夜游观景、玩水避暑）。落盘后用 `python3 -c` 一行正则抽 `名称/等级/热度/点评数`，只作排序与 `discoverySignals`。
- 热度代理：携程热度分与点评数（`ctripHeat`/`ctripReviews`）、维基 pageviews（`wikiViews30d`）、Flickr `interestingness`/faves（`flickrFaves`）、YouTube `viewCount`（`ytViews`）。只作候选排序与记录，不作门。

## 候选级质量筛选（可重放，不合格换候选、不落台账）

- homepage：百科正文 ≥ 600 字且有信息框或 ≥3 条结构化事实；非消歧义；名称能定位到行政区；0 张可用配图走 text_only。
- article 事实参考：游记正文 ≥ 1,500 字；含具体行程/交通/费用/时间/贴士 ≥3 项；发布 ≤ 3 年；非软广（推广词、店铺链接密度）；非纯图流水账；单篇不够多篇合参。
- image：长边 ≥ 1,600px；非扫描件/图表/地图/截图；主体切题（看原件）；水印为 `platform_logo|stock_agency` 排除；曝光/构图基本合格。
- video：时长 15s–5min；≥720p；实景为主；无二传平台烫印；能落到已发布或同轮实体。

## 试轮沉淀的候选级判据（可重放）

- Commons `LicenseUrl` 常为 `http://`，写 ingest 前统一改 `https://`，否则整份清单被 schema 拒绝。
- 视频候选先按 imageinfo 的 `size` 过滤：超过 `sourceAssetMaxBytes`（512 MiB）的源体 ingest 必拒，不要下载；4K 航拍原件常达 500 MB–1 GB。
- 说明文字或作者含「中新视频 / China News Service」等新闻机构二传的视频，画面几乎必带平台烫印，按 `platform_logo` 候选级排除；看 poster 前无法确认时，ingest 申报 `unknown`，由 author/reviewer 看 poster 后决定退轮。
- 超过约 1.5 亿像素的巨幅全景图无法被图片探测解码（`MIME_MISMATCH`），image 载体选 ≤ 50 MP 的原件。
- 下载后 `sha1` 与 imageinfo 不符（文件页被覆盖上传）按 `source_sha1_drift` 候选级换图，不重试。
- 条目自身配图里常混有位置图、地形图、旗徽、老照片、博物馆建筑照与「同名不同地」的图（如城墙条目里的他处遗址），image 载体必须看原件确认主体就是该实体。
- 头条百科头图 `License` 为空、`Copyright` 为 `no_copyright`/空时不能作资产，只能 text_only 或另取 Commons 图。

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

`status.license` 必须为 `creativeCommon`；`sourceUrl` 写 watch 地址，`directUrl` 写同一地址，`license` 写 `CC BY 3.0`，`licenseUrl` 写 `https://creativecommons.org/licenses/by/3.0/`，`creator` 写频道名，`hasAudio` 按实际，`rightsIssues` 由脚本按白名单派生 `verified`；`discoverySignals.ytViews` 记 `viewCount`。

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
