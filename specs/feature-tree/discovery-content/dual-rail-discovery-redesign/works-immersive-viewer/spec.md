# L3 Story：作品沉浸式浏览器 (`works-immersive-viewer`)

> 所属能力：[`dual-rail-discovery-redesign`](../spec.md)

> Journey / Scenario：[`JNY-003 / SCN-007`](../../../spec.md#scn-007)

> 设计归属：[L2 DEC-001](../design.md#dec-001)

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
- 单指水平手势按方向锁定前翻或后翻，纵向意图交给父级浏览；同一手势不得同时驱动两个导航轴。
- commit 收尾时长必须在 `320ms..520ms`，cancel 收尾时长必须在 `220ms..360ms`；落页前保持动态翻页层，最终帧与页码原子切换。
- 任意帧只允许一个 moving leaf、一条 seam/fold 与一条 free edge；图片书与文章复用同一 pageflip 几何语义。
- 媒体加载或失败状态在拖动与落页首帧期间保持冻结，随后淡入最新状态；Reduce Motion 下不显示翻页动态层，重试触达区至少 44pt。

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

- `components/pageflip/**` 与 `ui/content/article_reader/pageflip/**` 是文章翻页唯一实现边界。本 Story 不抽取新 DeckHost、painter、partition 或通用纹理类型，也不得为了图片适配改写文章 `Stack`、BACK replacement、诊断或同步 `completeAnimation` 时序。
- 文章既有 BACK 允许由当前静态页、上一页正面 replacement、当前页 bottom clip 与上一页 moving sheet 合成；这些是同一物理翻页的材质区域，不得被复制成额外 moving sheet。文章和图片在任意帧都只能出现一个 moving leaf、一条 seam/fold 与一条 free edge。
- 图片 moving sheet 每帧只绘制一张完整页面 front 或 back 材质。禁止两个纹理子页重叠、对子纹理使用 `FractionallySizedBox` 压缩、重复完整纹理起点，或以黑色/舞台底色填补本应由背面材质覆盖的区域。
- release 完成时，媒体适配层必须与文章一样强制应用 animation plan 最后一帧，再同步 `completeAnimation` 和 page index；动态 bottom 与目标静态页须同源。图片加载状态继续冻结到落平后的首个静态帧，随后才应用排队状态。
- 禁止：精品字样、媒体类型标识（图片/视频/文章）、页码（如 1/6）、常驻筛选 Tab。
- 图片/视频/文章默认均为深色沉浸背景 + 白色图标；文章不得因进入阅读而切换为独立白底阅读器。
- 媒体类型是筛选条件，不是一级导航；禁止顶部长期显示媒体筛选。
- 浏览器对外语义统一为 `all / image / video / article`，不暴露 `note` 命名。
- 左右滑动使用与文章同源的 `components/pageflip` 几何能力，经 `components/media/shared/pageflip/MediaPageFlipBook` 承载；媒体宿主按全屏横向位移判定 next/prev，并把手势转换为 pageflip 输入，禁止回退为 rubber-band `PageView` 主体验。
- 图片书展示层位于 `components/media/image/book/`，只接收图片 URL 列表、页码回调和边界 overflow 回调；禁止依赖 discovery/content DTO、Riverpod provider、GoRouter 或 `ui/**`。

<a id="req-010"></a>
### REQ-010 深色纸张主题默认与垂类适配

- 默认纸张主题必须按内容垂类映射，并允许用户在受支持主题间切换。

<a id="req-011"></a>
### REQ-011 翻书动画纸张材质同源

- 翻页正反面必须消费同一 `paperTexture` 来源，避免落页前后材质跳变。

<a id="req-012"></a>
### REQ-012 Markdown 实体标签进入实体主页

- Markdown 实体标签必须生成可访问链接，并导航到对应实体主页。

## 4. 契约引用

- canonical：`quwoquan_service/contracts/metadata/_shared/app_routes.yaml#workBrowser`
- canonical：`quwoquan_service/contracts/metadata/_shared/link_templates.yaml#entities.post.navigation`
- canonical：`quwoquan_service/services/content-service/contracts/content/post/projections/work_browser_item.yaml`
- canonical：`quwoquan_service/services/content-service/contracts/content/post/ui_config.yaml#work_format_filters`
- canonical：`quwoquan_service/services/recommendation-service/contracts/recommendation/recommendation_model_release/projections/intersection_reason.yaml`
- canonical：`quwoquan_service/services/content-service/tests/support/contract_fixtures/scenarios/content_scenarios.json`
- canonical：`quwoquan_service/services/content-service/contracts/content/post/ui_config.yaml#article_dark_paper_themes`
- canonical：`quwoquan_service/services/content-service/contracts/content/post/fields.yaml#entityRefs`
- canonical：`quwoquan_service/services/content-service/contracts/content/post/projections/content_post_detail_wire.yaml`
- canonical：`quwoquan_service/contracts/metadata/_shared/app_routes.yaml#homepageDetail`
- canonical：`quwoquan_app/lib/ui/content/article_reader/pageflip/host/article_read_only_book_deck.dart`

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
- THEN 各媒体恢复自身位置，图片书在前翻与后翻期间保持单一 moving leaf 和正确 face binding。

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

## 6. 依赖

- 前置要求：[`dual-rail-discovery-redesign`](../spec.md) 的范围、要求与 SIT。
- 下游结果：本 Story 声明的 GWT 可观察结果。
- 父级设计：[L2 DEC-001](../design.md#dec-001)

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

<a id="open-010"></a>
### OPEN-010 翻书动画纸张材质同源

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`；目标：pageflip 视觉/contract 测试断言 paperTexture 被正反面消费。
- 完成判定：`GWT-010` 对应行为满足且真实测试 `spec_ref` 有效。

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
