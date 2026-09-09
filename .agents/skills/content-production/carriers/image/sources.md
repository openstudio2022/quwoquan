# Image 来源

按实际来源小节读取。source request 由宿主明确给定，单次返回一页响应；翻页/改查询不自动执行。模板、分组与评分只在 [CARRIER](CARRIER.md)。

## commons · 已实现

- 来源名 `commons`。request 四选一：`{"query":"<地点/关键词>","limit":20}`、`{"category":"<不含 Category: 的类目名>","limit":20}`、`{"uploader":"<上传者>","limit":20}`、`{"article":"<中文维基条目>","limit":20}`；limit 必填且为 1..50。article 使用 zhwiki generator=images+imageinfo，仅保留 shared Commons 文件，不把本地上传冒充 Commons。可带 API 返回的 `continue`，只接受 continue/gcmcontinue/gaicontinue/gsroffset/gimcontinue；一次最多一页，不自动续页。
- 使用 MediaWiki imageinfo 获取图片 URL、sha1、尺寸、mime、extmetadata 和 1280px thumburl；仅保留 image mime，每个 File 是一个候选/资产。`--response` 用原始 API JSON；分页标记从保存响应查阅，不自动跟进。
- QI/FP/VI、地区类目和可信高产上传者可作优先入口，但不能仅凭上传者或文件名前缀推断实体。上传者不必是原作者，使用 Artist/作品页核实署名。
- 缺 license/creator 保持缺席；LicenseUrl 为 HTTP 时仅在核实同一公开 HTTPS 许可页后补充 selection，不能改许可原文。sha1 机械规范化为小写；原件 URL 查询参数保持，预览优先摘要核验原件，只有显式 discovery 才使用 API thumburl，不全局删 query 或猜宽度档。

## tuchong · 已实现

- 来源名 `tuchong`，request 用 `{"tag":"<标签>","page":1,"order":"weekly"}` 或 `{"siteId":"<摄影师 id>","page":1}`；单次取 `/rest/tags/<tag>/posts` 或 `/rest/sites/<id>/posts`，count=20。
- 解析 postList/posts、siteList 与 post.images：候选 `tuchong:<postId>`，逐图 id `tuchong:<userId>:<imgId>`；保留同作品多图及 views/favorites/comments/collected（实际返回数值才写）。CDN `/f/` 的真实下载尺寸与原图元数据可能不同，以 downloads index 为准。
- siteList 支持按账号 ID 索引的对象、含 site_id 的对象数组或 null；未知形状可解释报错。site 署名只写 uploader/uploaderUrl，原作者由宿主核实并填 selection.creator；纠正已有事实用精确 factEvidence。工具不自动填图虫协议/许可/accessPolicy。选中时记录核实的版权保留说明、条款 URL 与访问限制，不能补 CC。
- 周榜空不触发自动换 order；宿主在预算内另发明确请求。响应变 HTML、429 或挑战页即停本站本轮，不把解析错误当无候选继续撞站。

## pinterest · 已实现

- 来源名 `pinterest`，request `{"url":"https://www.pinterest.com/<用户>/feed.rss"}`，也接受实际存在的画板 `.rss`；只解析公开 RSS，不抓 SPA 搜索页、不登录。
- 解析 item 的 pin 链接、标题与 i.pinimg 图片，将已识别尺寸路径改为 originals 作为下载候选。该直链仍须实际取得确认，RSS 或 originals 不保证存在/高清；404 留缺口，不假称已取得。
- 候选按 pin 分组，当前模块仅提取 RSS 的一张图；不宣称支持多图轮播或视频 pin。画板/RSS 持有人不是原作者，原作者缺失如实记录“转载，原作者未标注”，不能写持有人姓名冒充原创。
- 工具不声明 license/creator/accessPolicy。选中时保留来源 pin、可查原作与权利说明；没有证据不得编造 CC 或授权。Pinterest 转载关系与公众可见性由现有权利记录/下游策略处理。

## flickr_openverse · 仅 Openverse API 已实现

- CLI 来源名 `flickr_openverse`，request `{"query":"<地点英文名>","page":1}`。实际仅请求 Openverse `/v1/images/`，固定 page_size=50、license 查询为 cc0/by/by-sa；候选的 source 是 openverse，id 为 `openverse:<id>`，sourceUrl 保留 foreign_landing_url。
- 保留响应里的 creator/creator_url/license/license_url 与每条原作品引用；查询过滤不是权利已核实，回原站查署名与许可。匿名配额/权限不保证可用；401/429 停止，当前没有 token 注册或自动刷新实现。
- Flickr API 没有对应实现，不能把此模块称为 Flickr SDK。宿主有合法 key 时可用 `flickr.photos.search`、`flickr.people.getPublicPhotos`、`flickr.photos.getInfo` 发现与取证，保留 sourceUrl、原图 URL、许可和署名；不把 license 数字代码未经核实转成 CC。
- Flickr photoset 或相同作者/日期不会自动成作品；只有明确合集证据才声明，当前不提供跨候选自动合并。

## inaturalist · 已实现

- 来源名 `inaturalist`，request `{"placeId":<地点 id>,"page":1}`，可选 taxonId。当前请求只设置地点、photos、per_page=100、页码及可选物种，**不自动限制 research grade 或 CC 许可**。
- 一个 observation 一个候选，所有 photos 保留原生顺序及 `inaturalist:photo:<id>`；square URL 转 original 为候选直链，license_code 逐图保存，attribution 作为来源说明。
- 观察者账号不独自证明每张照片作者；逐图 attribution/许可与地点、物种由宿主核实，不能用 observation 一份许可盖掉混合照片权利。适合自然保护区/观鸟等实体，敏感物种精确位置注意隐私。

## 其它公开媒体 · 宿主工具

头条百科配图、Flickr API、Unsplash/Pexels/Pixabay、历史档案等未在 image source 模块实现，确有需要才用宿主工具显式取证并准备 Data ingest；500px 等可作为发现线索，不宣称可批量抓取。禁止登录/验证码/DRM/挑战规避，不因站点知名就默认 open/verified。
