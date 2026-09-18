# L3 Story：作品沉浸式浏览器 (`works-immersive-viewer`)

> 所属能力：[`dual-rail-discovery-redesign`](../spec.md)

> Journey / Scenario：[`JNY-003 / SCN-007`](../../../spec.md#scn-007)

> 设计归属：[L2 DEC-001](../design.md#dec-001)、[L2 DEC-002](../design.md#dec-002)、[L2 DEC-003](../design.md#dec-003)、[L2 DEC-004](../design.md#dec-004)

## 1. 用户价值

作为浏览作品的用户，
我希望从所有作品入口进入同一沉浸式浏览器，并让翻页、互动和返回状态保持一致，
从而连续消费内容且不会因入口不同获得分叉体验。

## 2. 范围与非目标

### In Scope

- “作品沉浸式浏览器”的输入、可观察主路径、失败语义以及与父能力的交接。
- workBrowser 统一深链入口。
- 竖屏顶部系统层保留返回/更多；横向全屏顶栏为返回、作品标题与更多。
- 更多菜单媒体筛选（全部作品/图片/视频/文章）
- 图片书物理翻页、视频集胶囊、文章页尾页码。
- 底部工具栏作者/关注/赞转评 + 具象化交集句。
- `REQ-016 / GWT-015`：文章分页与渲染画布几何单源、页面饱满。
- `REQ-017 / GWT-016`：文章内嵌图片几何预留与加载四态稳定。
- `REQ-018 / GWT-017`：点击正文图片进入全文图片浏览层并恢复阅读位置。
- `REQ-019 / GWT-018`：沉浸系统层对齐轨道与底部 chrome 语义。
- `REQ-020 / GWT-019`：图片书加载等待滞回节奏与可恢复终态。
- `REQ-021 / GWT-020`：文章 page curl 默认开启并仅接受同一 runtime flag 的显式远端覆盖。
- `REQ-022 / GWT-021 / GWT-024 / GWT-025`：横向图片/视频显式局部旋转、统一五秒控件显隐、最新播放状态连续恢复。
- `REQ-023 / GWT-022`：底部导航中央 `+` 视觉容器收窄但保留 48pt 热区，关注在 Alpha 完整 App 旅程可用且 typed 失败局部恢复。
- `REQ-024 / GWT-023`：图片/视频共用有效比例、整栏透明三档与上下对称裁剪几何；整个沉浸周期隐藏 App 主导航。

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

- 竖屏默认态每个媒体只显示一份交集句；视频交集位于实际媒体下方的可选居中全屏入口之后、配文与时间轴之前，点击后进入对应详情，目标失效时提供可恢复降级。媒体与信息区消费 `REQ-024` 的同一整栏几何，不保留独立 current-time 行；竖屏时间轴遵循 `video-display-journey` 的 `GWT-004`，只在 scrub 显示目标时间/总时长。未来两行关联只预留实测布局输入，缺席时不占位、不创造关联事实；横向控件闭集按 `REQ-022`，不重复呈现交集句。

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
- 只有上游内容引用确实缺席才记录 absent；引用在场但获取器拒绝、校验失败或依赖不可用均记录 failure。Alpha 空 endpoint 合法，不得由业务解释为内容缺席。原始图片/封面/预览引用必须交给统一获取器，完整图片 full profile 不改变画布几何；私有 lease 校验与重试沿同一消费状态机。

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

- 竖屏普通模式的顶栏、caption、交集句、底部工具栏与文章正文必须共用同一横向对齐轨道：图片/视频阶段与媒体左右边界同源，文章阶段与正文 contentPadding 同源；底部 chrome 不得在该轨道之外叠加额外侧向收窄，机型底部安全区（home indicator/圆角）的保护只允许以垂直方向表达——在底部安全区之上抬升底部内容，不向中间收拢。横向局部旋转的控件安全区按 `REQ-022` 随宿主转换，不以本条竖屏轨道压缩横向媒体。
- 顶部返回与更多在沉浸面上为无底色纯白图标加柔和投影语义，颜色与投影收口在设计系统导航语义常量，触达区不小于 44pt；沉浸导航钮不得使用暗色圆底或毛玻璃。相机取景壳等操作钮为独立语义，不受本条约束。
- caption 收起态「全文」与展开态「收起」入口与配文同字重，颜色使用 worksAccent（与深色 mention 相同），不得加粗、不得使用系统或品牌 primary。「…」与配文同字重、同颜色。竖屏普通模式与横向全屏配文入口共用同一套样式，不因展示模式改字重或强调色。
- 图片作品配文优先当前图真实 caption，缺席则回退作品 body，不得把 title 当配文。
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

<a id="req-022"></a>
### REQ-022 横向媒体显式局部全屏、统一控件显隐与最新状态恢复

- 仅当前 image/video 的有效比例 `r>1`、查看器实际视口为竖屏普通模式且媒体可查看时，在实际媒体下沿之后水平居中显示“扩展图标＋全屏”。入口使用局部裁剪毛玻璃、低调半透明媒体深色面、细描边与浅色图文，视觉胶囊不扩散模糊到媒体或整栏，外层热区至少 44pt；顶部返回/更多仍保持无底色、无毛玻璃。入口空间参与 `REQ-024` 的同源几何；方形/竖向媒体、尺寸未知、初始化失败无有效目标及已经是宽视口时均不显示。删除独立右下 current-time 与小全屏图标整行；竖屏不因五秒无操作隐藏标题、底部作品工具栏或入口。
- 显式进入只把查看器及内部控件、弹层局部旋转 90°，固定手机上边对应横向画面左边，布局宽高、触摸坐标、弹层锚点与安全区同步转换；不改变 App 系统方向、不请求物理横屏、不读取方向请求结果作为进入条件、不随重力/方向传感器切模式。全 App 页面固定方向由 runtime owner 拥有，查看器只消费该约束，进入/退出不得释放或恢复另一套方向策略；不新建 route、第二播放器或重复请求播放源。真实窗口变宽只按实际约束排版，不重复旋转或新增桌面浏览器系统全屏能力。
- 横向安全视口使用单一三轨几何快照：左侧至少 44pt 的外部按钮槽只放返回，中间 `mediaStageRect`，右侧至少 44pt 的外部按钮槽顶部放更多、底部放收起；外槽与 stage 只随视口/安全区变化，不随素材比例变化。当前媒体在 stage 内按自然比例完整 contain 为 `visibleMediaRect`，允许在 stage 内留下 letterbox/pillarbox，禁止裁剪、拉伸或让媒体进入外槽；中央播放按钮锚定实际媒体中心。标题、时间轴、作者/关注与赞转评的左右边界只消费 `visibleMediaRect`，不得按整视口、stage 或外槽另算。横向顶栏的返回位于左外槽、更多位于右外槽，作品标题位于实际媒体内轨；标题可省略且无标题不编造文案，作者头像/名称/关注不得搬到顶部或重复显示。
- 横向底部作品工具栏保留作者头像、名称、关注与赞转评及真实计数的现有分组和排列：作者组左缘、操作组右缘与标题共同锚定 `visibleMediaRect` 左右边界；自己的作品沿用隐藏作者/关注、操作同行语义。右下收起位于右外槽并与顶部更多共用水平中心线，有独立至少 44pt 热区，不挤压关注或评论。视频中央提供唯一显式播放/暂停按钮；只有控件已显示后的独立点击命中该至少 44pt 热区才可切换一次播放 intent，隐藏态点击媒体、黑边或按钮原位置只显示控件，视频纹理与其他非按钮区域均不得播放/暂停。进度条位于整个底部作品工具栏上方，命中区不越过实际媒体内轨；视觉轨按 thumb 半径内缩，使 0%/100% 时整个 thumb 仍在媒体像素边界内。所有已知有效时长（含 ≤30 秒）在控件可见时都显示，中性白/灰轨道和白色拖动点，不使用红色或品牌红进度色。竖屏与横向均无常驻 current/total，只有 scrub 显示目标时间/总时长，无障碍仍可读取真实进度；图片无播放、时间或进度条。
- 横向媒体就绪并完成进入后，以最后一次有效交互结束为起点统一计时，满 5 秒隐藏返回、标题、更多、中央播放/暂停、作者/关注、赞转评、进度条、右下收起及专属渐变；播放、暂停与图片均同规则，不留常驻退出或时间。画布使用始终挂载、身份稳定的单一 interaction plane，禁止以隐藏态临时 recognizer 在 pointer-held 期间插入/移除；隐藏控件退出绘制、命中与无障碍树，但画面几何和播放 intent 不变。每个 pointer down 固定 `visibilityAtDown` 与 gesture epoch：隐藏态开始的短点只能幂等唤出并从 up 重新计满 5 秒，不得暂停/播放或在同一 up 再隐藏；可见态开始的下一次独立非按钮短点只能收起且不改变播放。普通 hold 只冻结当前状态和 deadline，不强制唤出；loading/buffering/failure、scrub、弹层与关键无障碍操作才是 require-visible blocker。长按/cancel 不反转显隐或播放，最后一指释放后重新完整计时。每次调度绑定 chrome/gesture epoch、interaction batch、当前 post/media/session identity 与绝对 deadline，迟到回调、position tick 和普通 rebuild 不得隐藏刚唤出的控件或修改新媒体；系统返回/Esc 与读屏可发现的显示控件/退出语义仍可用。
- scrub、buffering/loading/failure、评论/更多弹层、文本输入、关键无障碍焦点操作、路由离开及后台状态挂起隐藏计时并保持控件可见，交互结束、弹层关闭、路由/前台返回或恢复成功后从零重新计时；短视频局部时间轴 timer 与暂停 pinned 不得竞争横向整组计时器。播放中的 scrub 只更新虚拟 target，controller 持续播放且不额外发 pause/play；释放单次 seek，取消零 seek并保留自然推进的最新实际位置。评论在同一旋转宿主内按横向右侧面板呈现，更多使用局部菜单；原生分享、键盘等由系统呈现，不强行旋转系统 UI，返回后恢复查看器。平台强制保留的系统栏/手势指示不冒充已被隐藏，也不为隐藏它们请求方向切换。
- 返回优先关闭内部弹层；无弹层时左上返回、右下收起、系统返回/Esc 经同一退出逻辑只收起一层横向模式。保留同一 post、image/episode、评论和局部阅读上下文；位置和 intent 消费同一播放会话的最新已提交状态，不回跳进入时旧 snapshot，例如 00:10 进入、00:20 收起继续 00:20，横向手动暂停则竖屏仍暂停。
- 模式切换取消未提交 scrub/pageflip，不提交虚拟进度或半次翻页。横向禁止切作品、翻图与切集，但保留进度拖动、按钮和系统返回；收起后恢复竖屏浏览。作者主页、登录等独立页面按正常竖屏打开，标题与作者信息在往返后仍绑定同一作品，返回横向时恢复当前媒体与最新互动状态，不重新开始播放。整个沉浸周期隐藏 App 主导航且不占位，收起横向模式不恢复主导航；只有真正退出查看器才恢复进入前主壳状态，迟到回调不得覆盖其他页面。

<a id="req-023"></a>
### REQ-023 底部主导航与关注动作保持可达且局部恢复

- 底部导航中央 `+` 的视觉容器可适度收窄，但命中热区必须保持至少 48pt，且不得挤压相邻导航项或改变无障碍顺序。
- 关注动作必须在完整 `main_alpha` 的真实 App 旅程中经可见控件执行、由本地演练 typed port 提交并 readback，离开作者页/评论页再返回仍保持；对象端口的孤立成功或 API 成功不能替代 App 旅程。
- 关注 typed 失败只能在动作局部展示 canonical 文案与重试/登录恢复，不得把整个页面降级为 capability unavailable；取消不提交关注状态。

<a id="req-024"></a>
### REQ-024 图片视频共用整栏透明三档与上下对称裁剪

- `r` 为当前媒体经素材朝向元数据解释后的有效宽度/高度，`h=W/r` 为按屏宽等比显示的自然高度；不从手机姿态或媒体类型猜比例。尺寸未明时保留同源封面/既有占位及可达返回/更多，不凭默认 16:9 暴露横向入口，等待、超时与重试继续使用既有协议。
- `W、H` 为实际可绘制沉浸视口，含可绘制顶部状态栏背景与底部安全区，不扣不存在的主导航。`T` 为整个顶部状态栏背景及 App 操作区下沿，`B` 为收起态底部信息/作品工具栏整组上沿；底部组包含信息、进度热区、作者/关注、赞转评和安全区。宽媒体入口的完整热区与间距记为 `E`，无入口 `E=0`，普通区下界 `C=B−E`。完整区域只有普通 `[T,C]`、顶部整栏透明 `[0,C]`、上下整栏透明 `[0,H]`，高度为 `H0=C−T、H1=C、H2=H`。
- 当 `h≤H0`，媒体在普通区完整 contain，多余留白上 45%、下 55%；当 `H0<h<H1`，仍留在普通档并以 `[T,C]` 为窗口，上下各裁 `(h−H0)/2`，不部分侵入顶部。
- 当 `H1≤h<H`，使用 `[0,C]`，顶部状态栏背景与 App 顶栏同时整栏透明，底部组整体仍在媒体外黑色区域，上下各裁 `(h−H1)/2`；当 `h=H`，完整覆盖 `[0,H]` 且无裁剪；当 `h>H`，同用整屏窗口，上下各裁 `(h−H)/2`。等值仅容许正常像素舍入误差，不能额外扩大阈值。
- 三档均保持屏宽等比、禁止左右裁剪或拉伸；裁剪只改变展示窗口，不修改素材。9:16 是否全屏由当前视口决定，长屏不足整屏时退回适用档位，不能裁左右强行满屏；超长图按同一上下裁剪规则，不新增阈值或长图阅读器。45/55 只分配留白，不分配裁剪。
- 整栏透明指整栏背景透出同一媒体，文字、系统时间/电量图标、作者/关注与赞转评仍可读，不是隐藏文字或把半栏渐变透明。底部作品工具栏在整屏档为真实透明叠加，不允许不透明填充/模糊层盖住媒体；整个沉浸周期 App 主导航隐藏且不占位，不把主导航伪装成透明工具栏。平台不可绘制的系统区不声称已经透明。
- `B` 由收起态真实内容测量，缺席项高度/间距均为零；小屏/大字体优先收起可展开内容，控件保持可达，零高媒体区不能计为成功。普通播放、控件显隐或配文展开不得反复切档或重排媒体；显隐不释放已测空间。真实视口与媒体变化可重新选择档位，但需原子切换或整层转场，稳定帧及转场帧均禁止媒体边界扫过半个状态栏/工具栏。
- 图片、视频、图片静态页与翻页纹理消费同一显示窗口和对称裁剪结果；不为图片另建比例表、不重写 pageflip 主线。横向全屏按 `REQ-022` 在完整横向视口 contain，不误用竖屏裁剪档位。

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

- GIVEN 用户在圆弧/home indicator 机型的竖屏普通模式浏览图片、视频或文章作品，caption 文本超过收起态行数上限。
- WHEN 页面渲染顶栏、caption、交集句、底部工具栏与文章正文。
- THEN 各层左右对齐线一致（图片/视频与媒体边界同源，文章与正文 contentPadding 同源），底部 chrome 无额外侧向收窄，底部安全区保护只体现为垂直抬升。
- AND 顶部返回与更多为无底色白色图标加投影语义、触达区不小于 44pt；「全文」以 worksAccent 与配文同字重完整位于收起态最后一行行尾，不断字、不换行，省略号与配文同色同重，全文与收起不得加粗也不得使用系统或品牌 primary，竖屏与横向全屏配文入口样式相同。
- AND 图片作品配文优先当前图真实 caption，缺席则回退作品 body，不得把 title 当配文。

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

<a id="gwt-021"></a>
### GWT-021 宽媒体显式局部横向全屏与控件布局

- GIVEN 当前 image/video 有明确有效比例，查看器可能处于竖屏普通视口、宽视口或加载失败态。
- WHEN 用户查看入口、显式进入横向模式或改变手机姿态。
- THEN 仅 `r>1`、竖屏普通模式且有可查看目标时，在实际画面下方居中显示至少 44pt 热区的“图标＋全屏”；视觉胶囊使用局部 clip/blur、半透明媒体深色面与细描边，黑底、亮图和复杂画面上均可辨且不模糊媒体整层，顶部返回/更多仍无毛玻璃。无右下 current-time 行；方图、竖图、尺寸未知与失败无目标时无无效入口，宽视口不出现冗余入口或重复旋转。
- AND 显式进入仅将查看器、内部控件和弹层局部旋转 90°，宽高、触摸、安全区和弹层锚点一致；没有物理方向请求/捕获/恢复或传感器驱动模式转换，不创建第二播放器或重复请求播放源。
- AND 横向安全视口先形成固定左按钮槽、中间 stage、固定右按钮槽，媒体在 stage 内完整 contain；返回只在左外槽，更多/收起只在右外槽且水平同中心，三个外部按钮均至少 44pt 且不随素材比例横移。标题、进度条、作者/关注和赞转评共同对齐 contain 后实际媒体像素左右边界，误差不超过 1 physical px；中央按钮中心等于实际媒体中心。进度条命中/视觉/thumb 均不越媒体，0%/100% thumb 完整可见；含 29999/30000/30001ms 全部已知有效时长。图片无播放、进度或时间，未知时长不制造 seek 或虚假时间。
- AND 标题可省略但两侧按钮不受挤压，缺标题不编造；无常驻时间，只有 scrub 目标/总时长与无障碍真实进度语义。媒体不被 chrome 压缩，主导航整个沉浸周期不显示、不占位。

<a id="gwt-022"></a>
### GWT-022 导航中央动作与关注旅程真实可用

- GIVEN 用户在 Alpha 完整 App 进入含底部导航与作者关注入口的作品旅程。
- WHEN 用户命中中央 `+`、执行关注并往返评论/作者页，或关注返回 typed failure/取消。
- THEN `+` 视觉容器适度收窄但 48pt 命中区与无障碍顺序保持；关注成功由 UI 后续状态 readback 证明并跨往返恢复，失败局部恢复且页面其余能力可用，取消不提交。该结果必须来自真实 App 旅程，对象端口的孤立成功不得代填。

<a id="gwt-023"></a>
### GWT-023 图片视频三整栏档位与对称裁剪阈值

- GIVEN 图片与视频分别覆盖 21:9、16:9、4:3、1:1、3:4、9:16、匹配视口及超长比例，视口覆盖小屏、长屏、平板、大字与真实内容缺席/在场测量。
- WHEN 根据 `REQ-024` 的 `W/H/T/B/E/C` 计算 `h`，在 `H0/H1/H` 等值及阈值两侧呈现静态页、翻页纹理和转场。
- THEN `h≤H0` 为完整 contain 且留白上 45% 下 55%；`H0<h<H1` 仅普通区、上下各裁 `(h−H0)/2`；`H1≤h<H` 为顶部整栏透明、上下各裁 `(h−H1)/2`；`h≥H` 为上下整栏透明、上下各裁 `(h−H)/2`，匹配视口时为零。
- AND 所有结果全宽等比、无左右裁剪和拉伸；稳定帧与转场帧均无半栏覆盖，系统图标仍可读，整屏档底部工具栏绘制层真正透出同一媒体，App 主导航始终隐藏且不占位。相同比例/视口的图片、视频、静态页与翻页纹理窗口一致，横向 contain 不误走竖屏裁剪。
- AND 普通播放、暂停、控件显隐、scrub 和配文展开不改变档位/裁剪/媒体矩形；缺席内容无占位，小屏/大字收起可展开内容后仍有正面积媒体区和可达控件。以 `W=400、H=880、T=80、C=700` 为例，自然高度 660/760/880/960 分别上下各裁 20/30/0/40，不用固定素材比例代替阈值计算。

<a id="gwt-024"></a>
### GWT-024 横向统一五秒隐藏与轻点播放分离

- GIVEN 横向图片已就绪，或视频分别处于播放/暂停，全部普通控件可见，时钟可确定性推进。
- WHEN 自进入完成或最后有效交互结束经过 4.9 秒与 5 秒，用户短点或持续按住媒体/留白、点击中央播放按钮，或进行持续 scrub、buffering/loading/failure、打开弹层、输入、无障碍操作、路由离开及前后台恢复。
- THEN 4.9 秒控件可见，5 秒返回/标题/更多/播放/作者关注/赞转评/时间轴/收起及专属渐变全部隐藏，退出命中与无障碍树；播放、暂停和图片同规则，不留常驻退出/时间，媒体位置和裁剪完全不变。
- AND 稳定 interaction plane 在 pointer down 固定起始显隐意图：隐藏态短点（含中央按钮原位置）只幂等唤出、视频 intent/playCount/pauseCount 不变，同一 pointer-up 不再隐藏；可见态非按钮短点只收起且 intent 不变；只有下一次独立点击命中可见中央按钮才恰好提交一次播放/暂停。普通 hold 不强制唤出，按住超过 5 秒保持按下前显隐；release/cancel 不误触发反转并从零计满 5 秒。持续 scrub/buffering/loading/failure/弹层/输入/关键无障碍操作/路由离开/后台期间控件保持可见且不计时，结束或恢复后从零计时；position tick、普通 rebuild、旧 epoch 或旧 media/session 的迟到回调不得改写当前手势或隐藏新唤出的控件。
- AND 隐藏状态仍能通过系统返回/Esc 或可发现的无障碍动作退出；已知时长视频仅 scrub 显示目标/总时长，播放中的 scrub 不暂停且不额外发 play，end 单次 seek，cancel 零 seek并保留自然推进的最新实际位置。竖屏标题/工具栏/入口不自动隐藏，竖屏时间轴仍保留 ≤30 秒揭示后五秒和 >30 秒低亮度常显边界。

<a id="gwt-025"></a>
### GWT-025 横向收起与页面往返保持最新状态

- GIVEN 同一作品视频在 00:10 显式进入横向后播放到 00:20，或用户在横向手动暂停，图片已有稳定 image index，并可能存在未提交 scrub/pageflip 或内部弹层。
- WHEN 用户尝试切作品/翻图/切集、关闭弹层、使用左上返回/右下收起/系统返回/Esc，或打开作者/登录页面、评论/更多及系统分享后返回。
- THEN 横向浏览手势不改变 post/image/episode，不吞掉进度拖动、按钮和系统返回；模式切换取消未提交交互，不提交虚拟目标。返回先关弹层再收起模式，重复退出只作用一层。
- AND 收起后继续同一会话最新 00:20 而非 00:10，横向暂停仍暂停；作者/登录页按正常竖屏打开，内部弹层跟随旋转宿主，系统面板遵从平台。往返恢复同一媒体、标题/作者绑定、最新互动和局部阅读状态，不重复请求播放源或重新开始播放。
- AND 收起横向后恢复竖屏浏览操作但主导航仍隐藏；真正退出整个查看器才恢复进入前主壳状态，过期 timer/回调不得恢复已离开页面的控件或导航，也不得修改新媒体的位置/intent。

## 6. 依赖

- 前置要求：[`dual-rail-discovery-redesign`](../spec.md) 的范围、要求与 SIT。
- 下游结果：本 Story 声明的 GWT 可观察结果。
- 父级设计：[L2 DEC-001](../design.md#dec-001)、[L2 DEC-002](../design.md#dec-002)、[L2 DEC-003](../design.md#dec-003)、[L2 DEC-004](../design.md#dec-004)

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
- 影响或价值：尚缺实现或直接 `spec_ref`；目标：widget 测试断言竖屏默认态交集句按媒体类型只在规定位置显示一份，视频交集位于可选居中全屏入口之后、配文与时间轴之前，无 current-time 行；横向按控件闭集不重复交集句，点击后详情/导航降级正常。
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

<a id="open-015"></a>
### OPEN-015 局部横向全屏、统一显隐与最新状态恢复证据

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：`GWT-021`、`GWT-024`、`GWT-025` 已冻结局部旋转、标题/底部作者工具栏、局部毛玻璃入口、全时长横向时间轴、全部控件五秒隐藏、按住挂起/迟到 epoch 隔离和最新进度恢复；`works_immersive_viewer_widget__local_contract_test.dart` 与 `immersive_comment_panel__local_contract_test.dart` 的真实断言和 `spec_ref` 可作为各自覆盖子句的 local_contract 证据，尚缺全部结果子句的当前候选验证闭包及设备证据。不得将文件级绑定解释为每条子句或设备已通过；旧系统方向拒绝、常驻退出/时间与进入时旧位置恢复测试不代表当前验收。
- 完成判定：`GWT-021`、`GWT-024`、`GWT-025` 的全部结果子句由 geometry/Widget local_contract 覆盖宽媒体局部毛玻璃入口、局部坐标/弹层、安全区、29999/30000/30001ms、图片无播放/时间轴、4.9 秒/5 秒、播放/暂停、按住/取消后完整重计、迟到 epoch、持续不停播 scrub、buffering/loading/failure/弹层/路由挂起、隐藏不可命中、轻点不误播放、最新位置/intent 和禁切作品/翻图/切集；同一候选 Android/iPhone 真实设备及适用平板/宽视口 user_acceptance 直接 `spec_ref` 证明姿态不改变模式、进入/退出/back、标题作者/评论/分享往返与沉浸主导航不泄漏。全 App 固定方向设备证据由 runtime owner 单独负责，两个 owner 分别以自身当前候选证据裁定，不以对方历史 snapshot 或 OPEN 关闭为 local_contract 的前置条件；设备结果尚缺，不计通过。

<a id="open-017"></a>
### OPEN-017 三整栏几何与透明绘制设备证据

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：`REQ-024 / GWT-023` 的有效比例、三个整栏档位与上下等裁已有 `works_immersive_viewer_geometry__local_contract_test.dart` 的真实断言及 `spec_ref`，静态/翻页纹理一致性已有 `image_book_canvas_widget__local_contract_test.dart` 对应断言及绑定；尚缺全部结果子句的当前候选验证闭包和真实透明底栏/系统区域设备证据。测试源码在场不等于已执行通过，旧“竖视频 cover”、逐像素侵入或所有图片无条件 contain 的结果不能代替，也不能声称真实设备已全屏透明。
- 完成判定：`GWT-023` 的全部结果子句由纯几何与 Widget local_contract 覆盖 `H0/H1/H` 等值和两侧、八类代表比例、小屏/长屏/平板/大字、缺席内容、原子转场与显隐不改档；同一候选 Android/iPhone 设备证据证明系统图标可读、实际可绘制边界、底栏真实透明且非半栏覆盖、控件可达与主导航全程隐藏，平台强制系统区域按实记录，待证据不计通过。

<a id="open-016"></a>
### OPEN-016 底部中央动作与 Alpha 关注 App 旅程证据

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：`GWT-022` 的 48pt 命中区、Alpha 完整 App 关注、页面往返恢复和 typed 失败局部化尚无逐子句真实 App `spec_ref`；handler 单测只证明 port，不证明用户旅程。
- 完成判定：`GWT-022.t1..t2` 由布局 local_contract 与 Alpha Android/iOS user_acceptance 直接绑定，真实控件完成关注/readback、作者/评论往返、取消和 typed 失败，且页面不转为全页 capability unavailable。

<a id="open-014"></a>
### OPEN-014 canonical 发布物缺图片几何元数据

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：当前 canonical 发布物（`asset.refs.json`/`manifest.json` assets）不携带像素宽高（`PostArticleAsset` 契约已声明 NULLABLE `width`/`height` 但生产链路未填充），importer 投影后端侧恒走 4:3 后备比例，`GWT-016` 的元数据分支只能以测试注入验证，无法在真实 release 上生效；按真实比例预留的留白均匀度收益被阻断。
- 完成判定：数据生产链路（`1.download` 媒体冻结至 `article_media_contract`/manifest）为每个图片资产携带像素宽高并经 importer 投影到 `articleAssetManifest`，`GWT-016` 元数据分支在当前激活的 canonical immutable release 上可观察成立。
