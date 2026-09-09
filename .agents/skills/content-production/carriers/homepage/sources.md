# Homepage 来源

按当前实际来源小节读取；[CARRIER](CARRIER.md) 唯一拥有选材、主页模板与评分。producer 的 source 参数是模块名，request/response/output 是轮根相对路径；缺事实的候选可先保存，不自动补作者/许可。

## wikipedia · 已实现

- 调用来源名 `wikipedia`，request 为 `{"title":"<条目名>"}`。单次请求 zh.wikipedia API 的 extracts、info、pageprops、revisions，返回标题、正文、结构化 wikitext、revision 与消歧标记，落盘 source.md；离线可给原始 API JSON `--response`。
- 候选 id 使用 pageid 或 URL 摘要，sourceMarkdownPath 已带 homepage 前缀。工具不自动遍历类目、取 pageviews、找配图或选择百科主源；缺失条目返回空候选。
- 宿主核对首句/信息框的类型、行政区与实体名，读取实际许可与贡献者说明后在 selection 补事实；revision 留在原响应/候选，不声称 build-inputs 已映射全部发现元数据。
- 优先已有充实条目作骨架，补缺才查其它页；无需为“维基优先”拒绝唯一可用的头条百科来源。

## toutiao_baike · 已实现

- 来源名 `toutiao_baike`，request 为 `{"title":"<实体名>"}`；取得 `https://www.baike.com/wiki/<编码名称>`，解析 `__prefetch_doc_data__` 的 VersionContent、正文与 Infobox，保留版本（有则）及 source.md。`--response` 使用原始 HTML。
- 无公开结构化正文或正文为空即报错，不尝试绕过挑战页。工具不判断同名条目是否是人物；必须看首句、类型、地点，不能凭 URL 名称直接选中。
- 补充事实只来自确认同一实体的条目；缺许可/作者仍须如实取证，页面公开不等于图片 CC。当前模块不提取配图，不能声称已自动采集头图或确定图片权利。

## 实体前沿与携程景点榜 · 宿主工具

- 维基类目可按 5A/4A/3A、一级博物馆、历史文化名镇名村、自然保护区、省级文保渐进发现；携程按城市/地区榜与自然风光、户外活动、温泉、夜游等类型补充，另有有据的秘境/打卡地线索。先查 pool，不固定宣称类目数量。
- 携程公开榜形状为 `https://you.ctrip.com/sight/<城市标识>/s0-p<N>.html`。宿主检索/读页取得名称、热度、点评数、标签等，保留公开页面与取得时间；这里只是候选入口，不是百科主源。
- 当前没有 `ctrip_sight` 来源模块，也没有类别爬虫/pageviews 自动化；翻页与预算由宿主明确决定。热度与 `wikiViews30d` 等实测指标可填 discoverySignals，缺席不补零。

## 官方事实与配图 · 宿主工具

官方景区/文旅公告只用于定点补充可回查事实，不替代百科主源。已实现 homepage source 仅前述两种；其它 page/媒体由宿主显式准备本载体候选或 Data ingest，不能调用不存在的 homepage reference_page/commons 模块，也不读取 article/image 的私有工作区隐式供图。

配图可取同条目已核实图片或公开文件页，按本次实际许可/原作者/直链记录；无作者或许可不能造，不因头图 License 空就断言有授权。0 图合法，不为填封面冒用其它实体。
