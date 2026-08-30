# L3 Story：作品沉浸式浏览器 (`works-immersive-viewer`)

> 所属能力：[`dual-rail-discovery-redesign`](../spec.md)

> Journey / Scenario：[`JNY-003 / SCN-007`](../../../spec.md#scn-007)

> 设计归属：[L2 DEC-001](../design.md#dec-001)、[L2 DEC-002](../design.md#dec-002)

## 1. 用户价值

作为浏览作品的用户，
我希望从所有作品入口进入同一沉浸式浏览器，并让翻页、互动和返回状态保持一致，
从而连续消费内容且不会因入口不同获得分叉体验。

## 2. 范围与非目标

### In Scope

- “作品沉浸式浏览器”的输入、可观察主路径、失败语义以及与父能力的交接。
- workBrowser 统一深链入口。
- 顶部系统层只保留返回/更多。
- 更多菜单媒体筛选（全部作品/图片/视频/文章）
- 图片书物理翻页、视频集胶囊、文章页尾页码。
- 底部工具栏作者/关注/赞转评 + 具象化交集句。
- `REQ-016 / GWT-015`：文章分页与渲染画布几何单源、页面饱满。
- `REQ-017 / GWT-016`：文章内嵌图片几何预留与加载四态稳定。
- `REQ-018 / GWT-017`：点击正文图片进入全文图片浏览层并恢复阅读位置。
- `REQ-019 / GWT-018`：沉浸系统层对齐轨道与底部 chrome 语义。
- `REQ-020 / GWT-019`：图片书加载等待滞回节奏与可恢复终态。
- `REQ-021 / GWT-020`：文章 page curl 默认开启并仅接受同一 runtime flag 的显式远端覆盖。

### Out of Scope

- 父能力中由其他 Story 独立拥有的行为、能力级架构决定和实现任务。

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 作品沉浸式浏览器

- metadata/codegen/router/UI/test 中无旧三入口残留。

<a id="req-002"></a>
### REQ-002 旧内容深链入口收敛到 workBrowser

- metadata/codegen/router/UI/test 中无旧三入口残留。

<a id="req-003"></a>
### REQ-003 三类媒体内部导航状态信息与图片书体验

- 图片、视频与文章必须保持各自的页码、播放或阅读位置，并在返回列表后恢复原上下文。
- 文章纸张内容内允许显示页尾页码；作品浏览器的常驻系统层、图片/视频媒体层与正文图片全文浏览层不得显示页码或媒体序号。页码可见性与页码状态恢复是两个独立语义。
- 页码、分集、主题、caption、hydration 与原图授权等按作品保存的局部状态只在有界 resident/LRU 窗口内恢复；当前项不得被淘汰，超出回滑窗口后从 canonical 内容与默认位置重建，内存压力下只保留当前项，已过期原图授权不得复用。
- 单指水平手势按方向锁定前翻或后翻，纵向意图交给父级浏览；同一手势不得同时驱动两个导航轴。
- commit 收尾时长必须在 `320ms..520ms`，cancel 收尾时长必须在 `220ms..360ms`；落页前保持动态翻页层，最终帧与页码原子切换。
- 任意帧只允许一个 moving leaf、一条 seam/fold 与一条 free edge；图片书与文章复用同一 pageflip 几何语义。
- 媒体加载或失败状态在拖动与落页首帧期间保持冻结，随后淡入最新状态；Reduce Motion 下不显示翻页动态层，重试触达区至少 44pt。
- 媒体页码指示器位于文字之上，最多 6 个点且当前点与其它点共线。
- 「我的 post」底栏隐藏作者与关注入口，操作使用三等分同行布局。

<a id="req-004"></a>
### REQ-004 媒体筛选进入更多菜单

- 筛选项只出现在“更多”菜单并立即作用于当前浏览器；不得出现与浏览无关的 `onSave` 入口。

<a id="req-005"></a>
### REQ-005 具象化交集句作为推荐解释层

- 默认态每个媒体只显示一份交集句；视频交集位于总时长与时间轴上方，点击后进入对应详情，目标失效时提供可恢复降级。

<a id="req-006"></a>
### REQ-006 WorkBrowserItem 端云契约一致

- `WorkBrowserItem` 的字段与枚举必须来自 metadata/codegen，App 不得维护第二套解析模型。

<a id="req-007"></a>
### REQ-007 文章深色纸张主题与阅读设置

- 文章默认使用深色纸张主题；阅读设置可实时切换受支持主题，纯白纸不得作为默认。

<a id="req-008"></a>
### REQ-008 文章实体标签跳转实体主页

- Markdown 实体标签必须解析为可交互 span；点击后进入 `/homepages/{id}`，无效目标不触发错误导航。

<a id="req-009"></a>
### REQ-009 图片适配不得改变文章翻页引擎边界

- 图片书与文章必须消费 [L2 DEC-002](../design.md#dec-002) 的单一 pageflip 几何主线，在前翻、后翻、落页和加载状态变化中保持同一几何、材质与索引语义。
- 用户可见结果只由本 Story 声明：水平手势连续跟手，commit/cancel 后页面与页码原子一致，失败可恢复，Reduce Motion 可用，且不出现媒体分栏、额外 moving sheet 或 rubber-band `PageView` 主体验。
- pageflip 引擎不决定页码是否可见；所有呈现层必须复用 `REQ-003` 的页码边界，不得从媒体类型、当前索引是否存在或动画方向反推显示策略。

<a id="req-010"></a>
### REQ-010 深色纸张主题默认与垂类适配

- 默认纸张主题必须按内容垂类映射，并允许用户在受支持主题间切换。

<a id="req-011"></a>
### REQ-011 翻书动画纸张材质同源

- 翻页正反面必须消费同一 `paperTexture` 来源，避免落页前后材质跳变。

<a id="req-012"></a>
### REQ-012 Markdown 实体标签进入实体主页

- Markdown 实体标签必须生成可访问链接，并导航到对应实体主页。

<a id="req-013"></a>
### REQ-013 视频准备在 6 秒内进入可恢复终态

- 解码槽位等待、媒体源解析与原生播放器初始化共享一个 6 秒总预算；切集、返回、取消和 dispose 必须释放 controller 与槽位。
- 当前项可在全局解码预算允许时预热唯一 N+1 项的同源封面与媒体源；当前项永远优先，N+1 不自动播放，方向变更、切集、离开或内存压力必须立即取消并释放槽位。
- 等待时保留同源封面、返回与更多操作；300ms 后显示媒体区域内紧凑进度，3 秒显示“还在加载，请稍候”，6 秒切换到唯一恢复组错误且不保留动画。
- 未被分类的临时播放故障进入 `reloadLater` 并提供“重新加载”；明确不支持播放进入 `contentUnavailable` 并提供“返回”。单个视频失败只替换媒体区域，不遮挡作品浏览器。

<a id="req-014"></a>
### REQ-014 文章阅读器运营闭环与远端恢复

- 文章阅读器必须通过 product-ops catalog 记录 `enter`、`dwell`、`exit`、`error` 与 `recovery`；`dwell` 为 10% 采样，其余 lifecycle 事件全量采样。
- `error` 与 `recovery` 必须记录 metadata canonical `errorCode` 和 `recoveryAction`；`objectId` 只能进入 raw 明细，禁止进入 Prometheus label 或小时聚合维度。
- product-ops 必须从同一 catalog 提供 enter latency、lifecycle outcome 与 sampled dwell 指标，Elasticsearch 小时聚合、SLO 和告警必须消费这些同源事件。
- WorkBrowser 直达读取与文章详情 hydration 遇到 transient typed `RuntimeFailure` 时，必须展示可执行 Retry；Retry 只能重放同一 typed Remote reader，成功后恢复 canonical 内容，不得回退至 fixture、发现流或伪成功。

<a id="req-015"></a>
### REQ-015 release-bound production Remote 媒体消费与恢复

- `content.media_viewer` 从作品流或直达入口打开时，必须由 generated client 与 production Remote 读取 `ContentPostDetailSlice` 或同源作品投影；展示的 Post、ready `MediaAsset` 与交付引用必须属于当前环境已激活的同一 canonical immutable release，并与当前候选的 release 身份和 manifest digest 一致。
- 浏览器只拥有 hydration、展示、播放、交互入口与恢复体验；Post、MediaAsset、关系、隐私、举报和行为事实仍由 page contract 中各 participant 的公开 query/command 拥有，浏览器不得本地补写事实、复制 owner 或合成缺失媒体。
- release 漂移、媒体未 ready/不可见、delivery reference 无效或 typed Remote 失败时，页面必须保留返回与不受影响的浏览上下文，提供重放同一 Reader 的 Retry 或 canonical 返回动作；禁止回退 fixture、无关发现流、旧 release、空白页或伪成功。

<a id="req-016"></a>
### REQ-016 文章分页与渲染画布几何单源

- 分页测量与沉浸渲染必须消费同一份画布几何（内容宽高、顶部预留与 stage width 同源）；两者派生的 content size 必须相等，禁止分页按固定纸张比而渲染按真实视口的双真相源。
- 除最后一页外，每页尾部余量必须小于下一个内容块的高度，即不存在「本可放下却切页」；不得通过拉伸行距掩盖欠满。
- 同一篇文章在不同屏幕上的页数允许不同；跨屏一致的语义是每页留白规则与欠满上界一致，不是页数一致。

<a id="req-017"></a>
### REQ-017 文章内嵌图片几何元数据与加载四态

- 图片占位几何只由 `articleAssetManifest` 资产声明的像素宽高派生；元数据缺席时分页与渲染必须同取同一后备比例（4:3），两侧取值不得不同。派生比例 clamp 到版式区间（竖图下限 3:4、横图上限 2:1），超界部分由框内 cover 吸收。
- 加载中、成功、失败、缺席四种状态的转换不得改变占位框几何，不得触发重新分页或页码跳变；图片运行时解码尺寸不得作为分页输入。
- 加载中在统一阈值内保持纯色占位零动效，超阈值淡入轻量加载指示，超阈值完成时以短淡入呈现，不从指示态硬切。
- 加载失败在同一占位框内呈现可区分失败态并提供点击重试，重试清除负缓存后重放同一加载链路。
- URL 缺席（媒体端点或资产引用无法解析）对用户呈现与失败一致，但语义标识与观测记录必须独立（经 runtime 异常遥测留证据），不得与加载中、失败塌陷为同一无差别占位，也不得以伪装 URL 掩盖缺席。

<a id="req-018"></a>
### REQ-018 文章内嵌图片全文浏览层

- 点击正文任一图片打开只显示图片的全屏浏览层；点击事件必须被图片层吸收，不得同时触发文章翻页。
- 浏览层按文档顺序承载该文章全部图片资产，初始定位到被点击图片；左右翻页使用与图片作品同源的 pageflip 几何（在 `REQ-009` 声明的实现边界内），禁止回退为 rubber-band `PageView`。
- 浏览层遵守 `REQ-003` 的页码与系统层边界，并消费 `REQ-009` 的同源 pageflip 几何：不显示页码、媒体类型标识或常驻筛选，仅保留关闭/返回动作，视觉与图片作品沉浸浏览一致。
- 浏览层内单图加载失败只影响该图并保留重试，不阻断左右翻页与关闭；关闭后回到原文章页，阅读位置与页码不变。
- 浏览层打开与关闭经 `REQ-014` 声明的同一 product-ops catalog 链路记录；对象级 ID 只进入 raw 明细，不进入聚合维度。
- 浏览层只是展示层：不新建 route 或 page 对象，不复制或补写 Post、MediaAsset 事实。

<a id="req-019"></a>
### REQ-019 沉浸系统层对齐轨道与底部 chrome 语义

- 顶栏、caption、交集句、底部工具栏与文章正文必须共用同一横向对齐轨道：图片/视频阶段与媒体左右边界同源，文章阶段与正文 contentPadding 同源；底部 chrome 不得在该轨道之外叠加额外侧向收窄，机型底部安全区（home indicator/圆角）的保护只允许以垂直方向表达——在底部安全区之上抬升底部内容，不向中间收拢。
- 顶部返回与更多在沉浸面上为无底色纯白图标加柔和投影语义，颜色与投影收口在设计系统导航语义常量，触达区不小于 44pt；沉浸导航钮不得使用暗色圆底或毛玻璃。相机取景壳等操作钮为独立语义，不受本条约束。
- caption 收起态「全文」与展开态「收起」入口使用沉浸前景次级层级，不得使用品牌色。
- 收起态「全文」必须完整呈现在最后一行行尾，不得断字或被挤到下一行；截断必须按入口文本的实际预留宽度计算并经布局验证。

<a id="req-020"></a>
### REQ-020 图片书加载等待滞回节奏与可恢复终态

- 图片页开始加载即呈现深色占位且不改变翻页几何。等待指示采用滞回节奏：统一延迟阈值内零指示零动效，超过阈值淡入紧凑指示。
- 指示一旦出现必须保持最短展示时长，再经交叉淡出转场，任何完成时刻均不得产生指示闪现；延迟阈值、最短展示时长与转场时长收口在设计系统语义 token。
- 不同媒体允许按各自响应分布差异化延迟阈值，但共享同一滞回框架与 3 秒/6 秒全站节奏。
- 3 秒显示「还在加载，请稍候」（复用全站等待文案与时间真相源，不新建第二套常量），6 秒或候选链耗尽时切换到唯一恢复组失败态并取消在途加载，不保留动画；重试跳过延迟阈值立即出现指示，清除负缓存后重放同一候选链。
- 成功呈现使用短淡入，不从指示态硬切；Reduce Motion 下转场压缩或直切但滞回时长不变。单图失败只影响该页，不阻断翻页与返回。
- 媒体加载观测事件必须区分 success/failure/timeout/retry 并携带时长，可用于校准延迟阈值与真实分布的匹配度。

<a id="req-021"></a>
### REQ-021 文章 page curl 默认启用且配置单轨

- `enable_article_page_curl` 的默认值只由 `quwoquan_service/services/content-service/contracts/content/post/ui_config.yaml#enable_article_page_curl` 声明并经 codegen 进入 production runtime fallback，默认必须为 `true`；端侧阅读宿主与 pageflip deck 不得再声明第二个默认值。
- 远端 app config 只在显式携带 `enable_article_page_curl` 时覆盖该 fallback；字段缺席必须保留 metadata 默认值，显式 `false` 才可关闭卷角动效并进入既有降级分页器。
- 创作预览与沉浸消费均必须从 `contentFeatureFlagProvider('enable_article_page_curl')` 读取同一 effective runtime value，禁止按页面、机型或环境另设本地开关。

## 4. 契约引用

- canonical：`quwoquan_service/contracts/metadata/_shared/app_routes.yaml#workBrowser`
- canonical：`quwoquan_service/contracts/metadata/_shared/link_templates.yaml#entities.post.navigation`
- canonical：`quwoquan_service/services/content-service/contracts/content/post/projections/post_read_presentation.yaml#PostReadPresentation`
- canonical：`quwoquan_service/services/content-service/contracts/content/post/ui_config.yaml#work_format_filters`
- canonical：`quwoquan_service/services/recommendation-service/contracts/recommendation/recommendation_feature_profile_view/projections/intersection_reason.yaml`
- local_contract 对象构造器：`quwoquan_app/test/support/service/content_service/content/post/content_post_wire_test_builder.dart#contentPostReadModelWireExamples`；环境验收只读当前 activated immutable release，不引用静态 fixture。
- canonical：`quwoquan_service/services/content-service/contracts/content/post/ui_config.yaml#article_dark_paper_themes`
- canonical：`quwoquan_service/services/content-service/contracts/content/post/fields.yaml#entityRefs`
- canonical：`quwoquan_service/services/content-service/contracts/content/post/projections/content_post_detail_slice.yaml#ContentPostDetailSlice`
- canonical：`quwoquan_service/services/content-service/contracts/content/post/operations.yaml#GetPost`
- canonical：`quwoquan_service/services/content-service/contracts/content/post/projections/discovery_feed.yaml#releaseId`
- canonical：`quwoquan_service/services/content-service/contracts/media/media_asset/operations.yaml#GetMediaAsset`
- canonical：`quwoquan_service/contracts/metadata/_shared/app_routes.yaml#homepageDetail`
- canonical：`quwoquan_app/lib/service/content_service/content/post/presentation/article_reader/pageflip/host/article_read_only_book_deck.dart`
- canonical：`quwoquan_service/services/content-service/contracts/content/post/ui_config.yaml#enable_article_page_curl`

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 作品沉浸式浏览器

- GIVEN 内容创作者或浏览者具备有效身份，且父能力声明的输入与上游事实成立。
- WHEN 参与者执行“作品沉浸式浏览器”对应的公开行为。
- THEN metadata/codegen/router/UI/test 中无旧三入口残留。
- AND 失败时返回 canonical failure，且不产生伪成功事实。

<a id="gwt-002"></a>
### GWT-002 旧内容深链入口收敛到 workBrowser

- GIVEN 用户通过任一旧内容深链入口访问作品。
- WHEN 路由解析该入口。
- THEN 请求收敛到 workBrowser，且 metadata、codegen、router 与 UI 不保留旧入口。

<a id="gwt-003"></a>
### GWT-003 三类媒体内部导航状态信息与图片书体验

- GIVEN 用户在图片、视频或文章作品中连续浏览。
- WHEN 用户横向翻页、切换媒体或返回列表。
- THEN 各媒体恢复自身位置，图片书在前翻与后翻期间保持单一 moving leaf 和正确 face binding；BACK moving sheet 从 spine 进入可见页且不整体落在页外，动画后段的 recto、verso 与 current 均形成正面积可见分区。
- AND 长会话跨越局部状态窗口或发生内存压力时，当前作品位置仍可用，历史状态按 LRU 淘汰且过期原图授权回退 canonical 图片。

<a id="gwt-004"></a>
### GWT-004 媒体筛选进入更多菜单

- GIVEN 用户正在浏览作品。
- WHEN 用户从更多菜单选择媒体筛选。
- THEN 筛选立即作用于当前浏览器，且页面不展示无关的 onSave 入口。

<a id="gwt-005"></a>
### GWT-005 具象化交集句作为推荐解释层

- GIVEN 作品具有可展示的交集解释。
- WHEN 用户查看或点击不同媒体类型的作品。
- THEN 每个媒体只显示规定位置的一条交集句，并在目标不可用时提供可恢复降级。

<a id="gwt-006"></a>
### GWT-006 WorkBrowserItem 端云契约一致

- GIVEN 服务端返回 WorkBrowserItem。
- WHEN App 解析并展示该投影。
- THEN 字段和枚举仅来自 metadata 生成的契约，且校验与 codegen 一致通过。

<a id="gwt-007"></a>
### GWT-007 文章深色纸张主题与阅读设置

- GIVEN 用户打开文章作品。
- WHEN 用户查看默认主题或切换受支持的阅读设置。
- THEN 默认使用深色纸张主题，切换实时生效且纯白纸不作为默认。

<a id="gwt-008"></a>
### GWT-008 文章实体标签跳转实体主页

- GIVEN 文章 Markdown 包含有效或失效的实体标签。
- WHEN 用户点击解析后的实体标签。
- THEN 有效标签进入对应实体主页，失效标签不触发错误导航。

<a id="gwt-009"></a>
### GWT-009 深色纸张主题默认与垂类适配

- GIVEN 不同内容垂类的文章进入浏览器。
- WHEN 解析默认纸张主题。
- THEN 主题按垂类映射并保留受支持的用户切换。

<a id="gwt-010"></a>
### GWT-010 翻书动画纸张材质同源

- GIVEN 用户拖动或提交图片书与文章的翻页动画。
- WHEN moving sheet 展示正反面并落页。
- THEN 正反面消费同一 paperTexture 来源，且落页前后不发生材质跳变。

<a id="gwt-011"></a>
### GWT-011 Markdown 实体标签进入实体主页

- GIVEN Markdown 被解析为可访问的实体链接。
- WHEN 用户激活该链接。
- THEN 浏览器导航到对应实体主页，并保持无效目标的安全降级。

<a id="gwt-012"></a>
### GWT-012 视频等待与失败只占媒体区域

- GIVEN 用户在作品浏览器打开一个视频，播放器槽位、源解析或初始化持续等待。
- WHEN 等待达到 300ms、3 秒和 6 秒，或用户切集、返回与取消。
- THEN 同源封面保留，等待反馈按统一时间点变化，最迟 6 秒进入成功或恢复组错误终态。
- AND 旧 controller 不复活、槽位归零，重新加载或返回动作真实可用，作品列表仍可浏览。
- AND 仅当前项与唯一 N+1 可占用共享槽位；N+1 不自动播放，任何导航、方向或资源压力变化都取消过期预热，不抢占当前视频。

<a id="gwt-013"></a>
### GWT-013 文章阅读器事件与 transient Remote 恢复

- GIVEN 用户进入文章阅读器，并发生停留、退出、详情 hydration 失败或 Retry。
- WHEN App 上报 lifecycle 事件或用户执行 Retry。
- THEN 每个事件均通过生成的 product-ops payload 进入同一 catalog；error/recovery 带 canonical error/recovery 语义，Elasticsearch/Prometheus/告警不引入对象级高基数维度。
- AND transient typed Remote 失败后的 Retry 成功恢复 canonical 内容，且不会回退至 Mock、发现流或空白成功状态。

<a id="gwt-014"></a>
### GWT-014 immutable release 作品消费与交互恢复

- GIVEN 当前候选在目标环境激活了一份包含可见 Post 与 ready MediaAsset 的 canonical immutable release，用户从真实作品流或直达入口打开 `content.media_viewer`。
- WHEN App 通过 generated client 与 production Remote hydration 作品，用户浏览图片、播放视频或阅读文章，并执行一个由 participant 公开 command 拥有的交互或失败后的 Retry。
- THEN 页面展示的 Post、媒体交付引用与 release/manifest 身份均绑定同一候选，媒体可真实读取或播放，且不得以 fixture、旧 release、静态 URL、空结果或本地 DTO 冒充成功。
- AND 交互只交给对应 participant 的公开 command 并以 canonical readback 收敛；浏览器只拥有展示与恢复，不创建或修改 Post、MediaAsset、关系、隐私、举报及行为事实。
- AND typed Remote、release、媒体 ready/visibility 或交付引用失败时保留返回和未受影响的浏览状态，Retry 只重放同一 Reader，失败不得跳到无关发现流或伪造空白成功。
- AND 本场景只有在同一 commit、ContractGraph、candidate、environment 与真实 Provider 上取得 Android 物理设备及 iPhone 物理设备 `ReadinessResultBundle` 后才计通过；模拟器、Widget-only、blocked、failed 或 skipped 结果均不计。

<a id="gwt-015"></a>
### GWT-015 分页渲染几何单源与页面饱满

- GIVEN 同一篇多内容块文章在多种屏幕比例（长屏约 0.45、设计稿比 0.72、平板 4:3）下进入沉浸阅读。
- WHEN 分页引擎与沉浸渲染分别解析画布几何并完成分页。
- THEN 分页与渲染派生的 content size 完全相等。
- AND 除最后一页外，每页尾部余量均小于下一个内容块的高度。

<a id="gwt-016"></a>
### GWT-016 图片几何元数据消费与加载四态布局稳定

- GIVEN 文章包含带宽高元数据的竖图与横图、无元数据图片，且图片加载可被注入为快速完成、慢速完成、失败或 URL 缺席。
- WHEN 图片经历占位到成功或失败的状态转换，或资产引用无法解析。
- THEN 竖图与横图按元数据获得不同预留高度，无元数据时分页与渲染同取 4:3 且两侧相等。
- AND 阈值内完成不出现加载指示，超阈值出现指示后淡入成功，失败呈现可点击重试的失败态。
- AND 缺席呈现失败视觉但产生独立的语义标识与异常遥测。
- AND 全部状态转换前后图片占位框尺寸不变、文章总页数不变。

<a id="gwt-017"></a>
### GWT-017 文章内嵌图片全文浏览层

- GIVEN 用户在文章任一页看到正文图片，该文章含多张图片资产。
- WHEN 用户点击图片、在浏览层内左右翻页、关闭浏览层。
- THEN 打开只显示图片的全屏浏览层，初始定位为被点击图片，且文章页码不因点击改变。
- AND 浏览层可按文档顺序遍历全文全部图片，不显示页码或媒体类型标识。
- AND 关闭后回到原文章页，阅读位置不变；浏览层打开与关闭产生 catalog 事件。

<a id="gwt-018"></a>
### GWT-018 沉浸系统层对齐轨道与 caption 入口语义

- GIVEN 用户在圆弧/home indicator 机型上浏览图片、视频或文章作品，caption 文本超过收起态行数上限。
- WHEN 页面渲染顶栏、caption、交集句、底部工具栏与文章正文。
- THEN 各层左右对齐线一致（图片/视频与媒体边界同源，文章与正文 contentPadding 同源），底部 chrome 无额外侧向收窄，底部安全区保护只体现为垂直抬升。
- AND 顶部返回与更多为无底色白色图标加投影语义、触达区不小于 44pt；「全文」以沉浸前景次级层级完整位于收起态最后一行行尾，不断字、不换行。

<a id="gwt-019"></a>
### GWT-019 图片书等待滞回节奏与可恢复终态

- GIVEN 图片加载可被注入为阈值内完成、阈值边界完成、慢速完成、失败或超时。
- WHEN 等待经过延迟阈值、最短展示窗口、3 秒与 6 秒，或用户点击重试。
- THEN 阈值内完成全程无指示；阈值后指示淡入且出现后保持最短展示时长再交叉淡出，任何完成时刻不产生指示闪现。
- AND 3 秒出现慢提示且不引起布局重排，6 秒或候选链耗尽进入唯一恢复组失败态；重试立即出现指示并重放同一候选链。
- AND 观测事件按 success/failure/timeout/retry 区分并携带时长。

<a id="gwt-020"></a>
### GWT-020 文章 page curl 默认启用与显式远端覆盖

- GIVEN `ui_config.yaml` 声明 `enable_article_page_curl: true`，远端 app config 可能缺席该字段、显式为 `true` 或显式为 `false`。
- WHEN production runtime fallback 与远端配置合并，并由创作预览或沉浸文章阅读宿主消费 effective flag。
- THEN 字段缺席时 page curl 保持启用，显式 `true` 时保持启用，只有显式 `false` 时关闭并进入既有降级分页器。
- AND 阅读宿主、adapter 与 deck 的构造器均要求调用方显式传入该 effective value，不存在端侧第二默认值。

## 6. 依赖

- 前置要求：[`dual-rail-discovery-redesign`](../spec.md) 的范围、要求与 SIT。
- 下游结果：本 Story 声明的 GWT 可观察结果。
- 父级设计：[L2 DEC-001](../design.md#dec-001)、[L2 DEC-002](../design.md#dec-002)

## 7. 开放事项

<a id="open-001"></a>
### OPEN-001 统一作品导航与顶部系统层

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`；目标：widget 测试断言顶部无 works-format-tab-strip、无 works-top-progress-label。
- 完成判定：`GWT-001` 对应行为满足且真实测试 `spec_ref` 有效。

<a id="open-002"></a>
### OPEN-002 旧内容深链入口收敛到 workBrowser

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`；目标：metadata/codegen/router/UI/test 中无旧三入口残留。
- 完成判定：`GWT-002` 对应行为满足且真实测试 `spec_ref` 有效。

<a id="open-003"></a>
### OPEN-003 三类媒体内部导航状态信息与图片书体验

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`；目标：local_contract 覆盖 `MediaPageFlipBook` 全屏左滑 0→1、右滑 1→0、前翻/后翻 held dynamic layer 三面 face binding、斜向拖拽 rotation 与同尺寸，且 `ImageBookCanvas` 会同步当前图片页码并在第一页中心左滑立即进入跟手层。
- 完成判定：`GWT-003` 对应行为满足且真实测试 `spec_ref` 有效。

<a id="open-004"></a>
### OPEN-004 媒体筛选进入更多菜单

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`；目标：widget 测试断言筛选项与筛选行为，且 onSave 入口不存在。
- 完成判定：`GWT-004` 对应行为满足且真实测试 `spec_ref` 有效。

<a id="open-005"></a>
### OPEN-005 具象化交集句作为推荐解释层

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`；目标：widget 测试断言默认态交集句按媒体类型只在规定位置显示一份，视频交集高于总时长/时间轴，点击后详情/导航降级正常。
- 完成判定：`GWT-005` 对应行为满足且真实测试 `spec_ref` 有效。

<a id="open-006"></a>
### OPEN-006 WorkBrowserItem 端云契约一致

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`；目标：verify-metadata 与 codegen hash 校验通过。
- 完成判定：`GWT-006` 对应行为满足且真实测试 `spec_ref` 有效。

<a id="open-007"></a>
### OPEN-007 文章深色纸张主题与阅读设置

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`；目标：widget 测试断言默认主题映射、阅读设置选项、实时切换和白纸不作为默认。
- 完成判定：`GWT-007` 对应行为满足且真实测试 `spec_ref` 有效。

<a id="open-008"></a>
### OPEN-008 文章实体标签跳转实体主页

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`；目标：codec 测试覆盖实体标签解析为 span。
- 完成判定：`GWT-008` 对应行为满足且真实测试 `spec_ref` 有效。

<a id="open-009"></a>
### OPEN-009 深色纸张主题默认与垂类适配

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`；目标：widget 测试断言默认纸张与垂类映射。
- 完成判定：`GWT-009` 对应行为满足且真实测试 `spec_ref` 有效。

<a id="open-011"></a>
### OPEN-011 Markdown 实体标签进入实体主页

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`；目标：codec 与 widget/navigation 测试通过。
- 完成判定：`GWT-011` 对应行为满足且真实测试 `spec_ref` 有效。

<a id="open-012"></a>
### OPEN-012 作品沉浸式浏览器 验收证据

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺少能够证明“作品沉浸式浏览器”已满足当前规格的真实测试证据。
- 完成判定：`GWT-001` 对应行为满足且真实测试 `spec_ref` 有效。

<a id="open-013"></a>
### OPEN-013 immutable release 媒体消费双物理设备验收

- 类型：`external_blocker`
- 优先级：`P0`
- 准出影响：`block`
- 影响或价值：Data/content media sourceDigest 与发布物当前仍冻结，本场景保持 `WAIT_CONTENT`；尚缺同一候选的 canonical immutable release activation/readback、production Remote hydration、真实媒体读取/播放、交互恢复与 Android/iPhone 双物理设备结果，现有 local_contract、Widget、静态 URL 或历史 release 不得替代。
- 完成判定：`GWT-014` 的每条结果均由职责匹配的 production user_acceptance runner 直接 `spec_ref`，且 Android 与 iPhone 物理设备 `ReadinessResultBundle` 绑定同一 commit、ContractGraph、candidate、environment 与真实 Provider 并全部为 passed。

<a id="open-014"></a>
### OPEN-014 canonical 发布物缺图片几何元数据

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：当前 canonical 发布物（`asset.refs.json`/`manifest.json` assets）不携带像素宽高（`PostArticleAsset` 契约已声明 NULLABLE `width`/`height` 但生产链路未填充），importer 投影后端侧恒走 4:3 后备比例，`GWT-016` 的元数据分支只能以测试注入验证，无法在真实 release 上生效；按真实比例预留的留白均匀度收益被阻断。
- 完成判定：数据生产链路（`1.download` 媒体冻结至 `article_media_contract`/manifest）为每个图片资产携带像素宽高并经 importer 投影到 `articleAssetManifest`，`GWT-016` 元数据分支在当前激活的 canonical immutable release 上可观察成立。
