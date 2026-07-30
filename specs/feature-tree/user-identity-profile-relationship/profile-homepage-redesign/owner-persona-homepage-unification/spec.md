# L3 Story：Owner/Persona 一体化个人主页统一改版 (`owner-persona-homepage-unification`)

> 所属能力：[`profile-homepage-redesign`](../spec.md)
>
> Journey / Scenario：[`JNY-003 / SCN-009`](../../../spec.md#scn-009)
>
> 设计归属：[L2 DEC-001](../design.md#dec-001)

## 1. 用户价值

作为管理账号、Persona 或关系的用户，我希望我的主页互动转发双向列表与 owner/persona 隔离验收，从而安全地维持身份、画像与关系状态。

## 2. 范围与非目标

### In Scope

- 互动二级控制行
- type=share received/initiated 列表
- cursor 分页、双方向缓存、seen/read、impact、隐私与观测

### Out of Scope

- 主页头部与一级 Tab
- 点赞、评论、浏览列表实现
- 独立转发页面与公开转发资产

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 互动导航保持两层且只改转发

- 本 Story 只改变转发互动；点赞、评论与浏览列表的内容、顺序和点击目标不得改变。

<a id="req-002"></a>
### REQ-002 收到与我发起文案和行结构正确

- 行高、头像、角标、预览、间距、字号、分割线和 44pt 热区符合 token 契约。

<a id="req-003"></a>
### REQ-003 预览与失效降级完整

- 所有目标仍保留时间、转发关系和可进入的用户身份。

<a id="req-004"></a>
### REQ-004 received 未读和真实影响归因

- 切换到 received 不会批量标记全部已读。

<a id="req-005"></a>
### REQ-005 双方向缓存分页和竞态安全

- cursor 全序无重复遗漏，底部状态完整。

<a id="req-006"></a>
### REQ-006 点击解析优先级一致

- 不存在同一行两条不同内容跳转路径。

<a id="req-007"></a>
### REQ-007 私有列表与Persona隔离

- 我发起的转发不进入公开主页、搜索索引、交集或影响数字。

<a id="req-008"></a>
### REQ-008 转发列表观测闭环

- 指标可按方向、目标类型、缓存命中、失败码和环境聚合。

<a id="req-009"></a>
### REQ-009 对外路由稳定且端云身份语义统一

- 对外路由与端云公开身份契约统一为 `/user/{userHandle}`；`ProfileSubject` 只承载对象类型与 canonical subject id，不再保留 `username` 路由别名。
- 编辑入口进入统一的资料编辑流。
- “是否同步给 owner / 其它 persona” 必须进入写入契约，不能只停留在前端临时状态。
- `我的主页` 与 `他人主页` 最终都落到统一的 `ProfileShell`。
- 头部布局统一为：头像侵入背景约 `1/3`，名字与资料主体在 profile 区 `2/3`，个人介绍独立成块。
- 用户资料区顶部必须始终锚定在背景图底边，不允许出现“背景图在拉伸，但资料区没有下移”或“资料区下沉到背景图底边以下”的断层。
- 一级 Tab 下的内部列表不能再误触发头图拉伸。
- 个人主页整体升级到统一 iOS 风格：优先使用 Cupertino 风格按钮、分段、底部动作和图标语义。
- 在头像触顶前，背景图、头像、用户名、资料区、一级 Tab 和列表必须处于同一主滚动坐标系。
- 二级 Tab 不进入壳层吸顶体系，只属于各一级 Tab 的内容区，并随列表滚动；回滑到对应区域时必须自然回显。

## 4. 契约引用

- canonical：`quwoquan_service/services/user-service/contracts/account/user_account/ui_config.yaml`
- canonical：`quwoquan_service/services/content-service/contracts/content/profile_interaction_activity_view/operations.yaml`
- canonical：`quwoquan_service/services/content-service/contracts/content/post/fields.yaml`
- canonical：`quwoquan_service/services/content-service/contracts/content/post/operations.yaml`
- canonical：`quwoquan_service/contracts/metadata/_shared/ui_surfaces.yaml`
- canonical：`quwoquan_service/services/content-service/contracts/content/post/errors.yaml`
- canonical：`quwoquan_service/services/content-service/contracts/content/content_behavior_fact/behaviors.yaml`

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 互动导航保持两层且只改转发

- GIVEN 当前用户进入我的主页互动 Tab。
- WHEN 二级控制行完成渲染并选择转发。
- THEN 一级保持记录/互动/足迹。
- THEN 二级为点赞/评论/转发/浏览和收到的/我发起的。
- THEN 页面不存在全部、互动明细、第三行导航或独立转发页。

<a id="gwt-002"></a>
### GWT-002 收到与我发起文案和行结构正确

- GIVEN received 与 initiated 均存在记录、讨论、附言和无附言 fixture。
- WHEN 用户分别查看两个方向。
- THEN received 显示“用户名 转发了你的记录/讨论”。
- THEN initiated 显示“你转发了 用户名 的记录/讨论”。
- THEN 附言最多两行，每次转发独立成行。

<a id="gwt-003"></a>
### GWT-003 预览与失效降级完整

- GIVEN 图片、视频、文本、讨论和四种 availability fixture 已加载。
- WHEN 转发行或媒体加载失败被渲染。
- THEN 图片使用 aspectFill，视频只显示封面和播放图标，文本和讨论最多两行。
- THEN deleted/private/reviewing/author_deactivated 显示明确文本，不显示空白灰图或加载失败大块。

<a id="gwt-004"></a>
### GWT-004 received 未读和真实影响归因

- GIVEN received 行具有 unread、可选 impact 文案与可选 evidence destination。
- WHEN 行可见超过 50% 持续 1 秒，或用户打开详情/影响明细。
- THEN 逐条上报 impression 与 seen，打开详情逐条 read。
- THEN 只有服务端完整返回 impactPrimaryText 才展示，且必须同时有 impactDeepLink 才可点击。
- THEN initiated 不显示未读、已读或影响数据。

<a id="gwt-005"></a>
### GWT-005 双方向缓存分页和竞态安全

- GIVEN received 与 initiated 各有超过 20 条稳定排序事件。
- WHEN 用户切换方向、滚动、预加载、下拉刷新并快速来回切换。
- THEN 两个方向分别保存 items/cursor/scrollOffset/loading/lastFetchedAt/error。
- THEN 缓存 5 分钟内立即显示，过期后台刷新，旧 generation 不覆盖当前结果。
- THEN 距尾 5 条预加载，刷新只作用当前方向。

<a id="gwt-006"></a>
### GWT-006 点击解析优先级一致

- GIVEN shareRecord、原目标和失效目标三类 fixture 已准备。
- WHEN 用户点击整行、预览、头像、昵称或影响结果。
- THEN 行和预览统一按可用 shareRecord、可用原目标、失效不跳转解析。
- THEN 头像和昵称按方向进入 actor 或 counterpart 主页。
- THEN 影响结果只进入 metadata 枚举的传播来源明细。

<a id="gwt-007"></a>
### GWT-007 私有列表与Persona隔离

- GIVEN 当前账号具有多个 persona，另有他人主页和拉黑关系 fixture。
- WHEN 用户访问他人主页、切换 persona 或直接调用/deep link 到转发互动。
- THEN 他人主页不展示 share 筛选且不发请求。
- THEN 服务端只允许 owner 的 active persona 读取，越权返回结构化 401/403。
- THEN 分身切换立即清空旧缓存，拉黑与匿名身份按服务端投影处理。

<a id="gwt-008"></a>
### GWT-008 转发列表观测闭环

- GIVEN 用户进入转发、切方向、曝光、点击、刷新和分页。
- WHEN 对应动作发生。
- THEN 上报规格定义的 8 个 share interaction 事件。
- THEN 公共参数包含 personaId/direction/interactionId/targetKind/targetId/shareRecordId/source。
- THEN 列表浏览事件不复用执行转发行为事件。

## 6. 依赖

- 前置要求：[`profile-homepage-redesign`](../spec.md) 的范围、要求与 SIT。
- 下游结果：本 Story 声明的 GWT 可观察结果。
- 父级设计：[L2 DEC-001](../design.md#dec-001)
