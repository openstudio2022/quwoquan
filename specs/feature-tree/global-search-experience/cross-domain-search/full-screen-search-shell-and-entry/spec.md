# L3 Story：全屏搜索壳与入口 (`full-screen-search-shell-and-entry`)

> 所属能力：[`cross-domain-search`](../spec.md)
>
> Journey / Scenario：[`JNY-005 / SCN-011`](../../../spec.md#scn-011)
>
> 设计归属：[L2 DEC-001](../design.md#dec-001)

## 1. 用户价值

作为执行搜索的用户，我希望从任一一级页面进入同一全屏搜索：初始态展示记录与管理入口，输入后切换为实时联想态，从而以稳定视觉和交互心智找到可理解并可继续操作的结果。

## 2. 范围与非目标

### In Scope

- 默认搜索页的最近搜索、猜你想搜、热门圈子、热门地点。
- 输入过程的联系人、聊天记录、已加入圈子、已关注地点、已关注的人、推荐搜索词。
- 正式结果页固定 Tab：小趣、全部、交集、图片、视频、长文。
- 全部 Tab 的已连接区前置与未连接发现区按比例成组混排。
- 指定类别 Tab 的纯内容消费流。

### Out of Scope

- 独立圈子、地点、人一级 Tab。
- 输入过程中展示未连接对象或正式内容结果。
- 维护第二套搜索接口或 UI 内业务假数据。

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 默认搜索页负责激发搜索而不是展示正式结果

- 用户无需输入即可看到继续搜索和产生兴趣的真实启发内容。

<a id="req-002"></a>
### REQ-002 输入过程本地结果先出且云实体不阻塞

- 本地结果不被聊天同步、圈子预热或云实体延迟阻塞。

<a id="req-003"></a>
### REQ-003 全部 Tab 先展示已连接区，再展示未连接发现区分组混排

- 全部 Tab 同时满足“已连接优先”和“未连接按比例发现”的信息架构。

<a id="req-004"></a>
### REQ-004 指定类别 Tab 只展示该类别的消费流

- 每个指定类别 Tab 都与全部 Tab 的聚合视角区分清晰。

<a id="req-005"></a>
### REQ-005 统一全屏搜索首页初始态与输入后的联想态

- 统一全屏搜索首页初始态与输入后的联想态。
- 统一首页、聊天、讨论、助手页的搜索入口行为。
- 全局搜索必须是唯一全屏全局浮层。
- 页面视觉必须遵循 iOS 原生 UX 规则与 design token。
- 搜索入口不得在各页自行维护第二套 path、surface、route 行为。
- “更多联系人 / 更多聊天记录”只能在当前页内联展开，不得跳到新中间页。
- 搜索框尾部只保留清除按钮；输入框内部不得再表达请求进度。
- 本地联系人、会话、消息、常用项并行查找并在 1.5 秒内各自结算；聊天同步与圈子预热只能后台 best-effort，不能阻塞联想。
- 云端实体主页从请求开始即获得 6 秒总预算；3 秒只是阻塞空白页的慢提示，不得在 3 秒重新发请求或延长 deadline。
- query 变化、清空、返回与页面销毁必须取消 transport、递增 generation 并清理计时器；旧响应不得覆盖新 query。

## 4. 契约引用

- canonical：`specs/feature-tree/global-search-experience/spec.md`
- canonical：`quwoquan_service/contracts/metadata/_shared/search_contract.yaml`
- canonical：`quwoquan_service/contracts/metadata/_shared/search_objects.yaml`
- canonical：`quwoquan_service/services/search-service/contracts/search/search_request_fact/operations.yaml`
- canonical：`quwoquan_service/services/entity-service/contracts/entity_homepage/homepage/operations.yaml`
- canonical：[`xiaoqu-entry-handoff` GWT](../xiaoqu-entry-handoff/spec.md#gwt-001)

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 默认搜索页负责激发搜索而不是展示正式结果

- GIVEN 用户打开全局搜索页。
- GIVEN 搜索框为空。
- WHEN 最近搜索与默认推荐数据加载完成。
- THEN 页面展示最近搜索、猜你想搜、热门圈子、热门地点。
- THEN 最近搜索服务端最多保留 12 条，compact 默认 2 列 5 行；超过首屏容量时可展开。
- THEN 猜你想搜来自 search-service term-heat 读模型；热门圈子/地点来自各对象 Remote query，不维护 UI 业务假数据。
- THEN 默认页不展示图片、视频、长文等正式结果流。

<a id="gwt-002"></a>
### GWT-002 输入过程本地结果先出且云实体不阻塞

- GIVEN 用户在全局搜索页输入关键词。
- WHEN 本地联系人、会话、消息、常用项与云端实体主页开始并行查询。
- THEN 搜索框尾部只有清除按钮，输入框内没有 spinner。
- THEN 本地域各自在 1.5 秒内结算并先于慢云端结果展示。
- THEN 发布态云实体作为既有“搜索网络结果”段预览，不新增第五分段。
- THEN 输入“钱”时包含匹配命中“东钱湖”，点击后进入对应实体主页。
- THEN 无命中的分组隐藏。
- THEN 不展示未关注圈子、未关注地点、未连接的人、图片、视频、长文正式结果。
- THEN 点击搜索按钮进入正式结果页，默认 Tab 为全部。

<a id="gwt-003"></a>
### GWT-003 全部 Tab 先展示已连接区，再展示未连接发现区分组混排

- GIVEN 用户提交关键词进入正式搜索结果页。
- GIVEN 结果池包含已连接结果和未连接结果。
- WHEN 用户停留在默认全部 Tab。
- THEN 顶部 Tab 固定为“小趣｜全部｜交集｜图片｜视频｜长文”。
- THEN 已连接区按聊天记录、联系人、已加入圈子、已关注地点、已关注的人、已互动内容顺序展示，每类最多一组。
- THEN 未连接发现区按交集、圈子、地点、人、图片、视频、长文同类成组，并按匹配池数量与相关度比例混排。
- THEN 发现区不展示“查看更多”，继续下滑加载下一批组。
- THEN 当前 query/tab generation 只调用一次 canonical `POST /search`，App 不做顺序 fan-out。

<a id="gwt-004"></a>
### GWT-004 指定类别 Tab 只展示该类别的消费流

- GIVEN 用户在正式结果页切换到交集、图片、视频或长文 Tab。
- WHEN 对应结果池加载完成。
- THEN 交集 Tab 展示交集概览、交集推荐区和交集发现流，每张卡显示交集原因。
- THEN 图片 Tab 只展示双列图片瀑布流，不展示图片组标题。
- THEN 视频 Tab 只展示双列视频瀑布流，不展示视频组标题。
- THEN 长文 Tab 只展示单列长文阅读流，不展示长文组标题。
- THEN 小趣 Tab 单独展示总结、推荐方向、相关对象和可继续追问，不参与全部混排。

## 6. 依赖

- 前置要求：[`cross-domain-search`](../spec.md) 的范围、要求与 SIT。
- 下游结果：本 Story 声明的 GWT 可观察结果。
- 父级设计：[L2 DEC-001](../design.md#dec-001)
