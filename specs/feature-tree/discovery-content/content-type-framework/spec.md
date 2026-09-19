# L2 Business Capability：内容类型框架 (`content-type-framework`)

> 所属领域：[`discovery-content`](../spec.md)
>
> 设计引用：[本层 design.md](./design.md)

## 1. 能力目标

为内容流提供正交的对象身份、展示面、布局策略与可选配方四层模型，禁止取值组合推导新概念；通过生成闭集能力协商与云侧过滤实现端云解耦扩展；同步退役 `ContentIdentity` / `micro` / `moment` 全栈残留。

## 2. 范围与非目标

### In Scope

- 正交字段四层模型：`ContentType`（对象身份）、`ContentUiSurface`（展示面）、`SurfaceLayoutPolicy`（面布局）、`FeedPresentationRecipe`（可选配方）。
- 能力协商：生成 `ClientContentPresentationContract` 闭集随请求上送，云按集合差过滤候选，窗口键含 `contractDigest`。
- 扩展手册：新增类型/面/配方的契约顺序、兼容替换规则、未知值处理终态、禁止默认猜测。
- 同步退役：删除 `ContentIdentity`（`moment`/`work`）、`ContentType.micro`、`PromotePostToWork` 的契约、服务、App、Data 与规格残留。

### Out of Scope

- 新卡片视觉设计（只登记现有 recipe）、推荐模型重训、gathering 插卡、圈子 feed 独立对象化。
- 改变首页手机默认 1 列、主页手机默认 2 列的产品数字（只收口到 Surface 策略）。

## 3. Journey / Scenario 贡献

- [`JNY-004 / SCN-001`](../../spec.md#scn-001)
  - 本能力处理：组合本目录 Story 的可观察行为。
  - 本能力输出：对象 × Surface × 面布局 × 可选配方四层正交模型，每层单字段单责，禁止多字段交叉推导；生成闭集能力协商与云过滤实现端云解耦扩展；`micro` / `ContentIdentity` 同步退役。
  - 失败时终态：可解释、可恢复且不伪造成功。

## 4. Story



- [`creation-mode-and-surface-ia-unification`](./creation-mode-and-surface-ia-unification/spec.md)：用户只需要在入口选择开始动作，系统能根据真实媒体结果进入图片或视频编辑状态，且发布 payload 的 `contentType` 与最终媒体类型一致。
- [`creation-tagging-ia`](./creation-tagging-ia/spec.md)：各类型编辑页提供可选标签，未选择标签不得阻断发布。
- [`markdown-article-kernel`](./markdown-article-kernel/spec.md)：小屏或可访问性大字号下统一降级为 `fullWidth`。
- [`unified-presentation-model`](./unified-presentation-model/spec.md)：同一三类 Post 跨面保持正文、媒体与互动事实一致，未知项隔离且不恢复旧投影兜底。

## 5. 能力要求

<a id="req-001"></a>
### REQ-001 对象身份正交字段：写入时确定，读侧只翻译

- Post 权威字段 `ContentType`：`image` | `video` | `article`（删除 `micro`）。
- 内容形式区分点：**是否进入长文编辑器、是否有独立正文**。
  - `article`：文章编辑器产出，包含纯文字与富文图文混排；正文是主体，可在正文语义文档中组织图片或视频，不能按有无媒体判型。
  - `image`：图片为主体，可有或无短配文；图片集合与配文分区呈现，不进行正文段落与图片混排（不进文章编辑器）。
  - `video`：视频为主体，文字只能短配文（不进长文编辑器）。
- 退役整个 `ContentIdentity`（`moment`/`work`）；现网 `workBrowser` 路由保留为侵入式 Surface 的实现壳，不再表示内容身份。
- 存量 `contentType=micro` 只允许在一次性数据迁移中分类（有权威视频→`video`、有权威图片无视频→`image`、纯文字或文字为主→`article`、冲突或无法分类→typed fail-closed 不进公开 feed）。

<a id="req-002"></a>
### REQ-002 展示面类型化闭集：页面身份，禁止字符串 source 冒充

- `ContentUiSurface` v1 闭集与现网页面对齐：
  - `homeFeed`：首页内容流（频道变体不是新 Surface 种类）。
  - `profileWorks`：我的/他人主页「记录」作品格（mine/other 是 viewer 模式，不是两种 Surface）。
  - `mediaImmersive`：侵入式媒体浏览器（现 `WorksImmersiveViewer` / `workBrowser`）。
  - `articleReader`：文章沉浸阅读（可与 `mediaImmersive` 共用路由、typed mode；对外仍是独立 Surface 语义）。
  - `homepageDetail`：实体主页详情。
- 侵入式浏览器是与 collection 面对等的一等 Surface，不是详情别名也不是内容类型。
- 跳转边（Surface 之间，不是类型推导）：
  - `(homeFeed | profileWorks) + post.image|video` → `mediaImmersive`
  - `(homeFeed | profileWorks) + post.article` → `articleReader`
  - `homeFeed + entityHomepage` → `homepageDetail`
- 来源归因用类型化 `ContentUiSurface`，删除 `'home_feed'` / `'profile'` / `'profile_moment'` 字符串。

<a id="req-003"></a>
### REQ-003 面布局策略：页面 × 视口，渲染时计算，不进对象字段

- 列数是 Surface 属性对窗口尺寸的函数，不是对象字段，也不是推荐字段。
- v1 布局矩阵（冻结进各 Surface 的 ui_config，不进 Post）：
  - `homeFeed` × compact：1 列（频道可覆盖 `phoneColumns`）。
  - `homeFeed` × expanded/PC：按可用宽度升到 N 列（上限 4）。
  - `profileWorks` × compact：2 列。
  - `profileWorks` × expanded/PC：2–4 列同一网格函数。
  - `mediaImmersive` / `articleReader`：1，全屏，与窗口列数无关。
  - `homepageDetail`：对象页壳，不是 post 网格。
- 禁止：把「单列/两列」写成 recipe 成员；按 `contentType` 推断列数；首页与主页两套 breakpoint 长期分叉。

<a id="req-004"></a>
### REQ-004 可选获取时配方：仅当同一 Surface 有多种卡片家族

- `FeedPresentationRecipe` 只挂在首页排序窗口的项上。个人主页作品格、侵入式浏览器不消费 recipe。
- 首页 v1 recipe 闭集：`coverMediaCard`（现 `_HomeRelationPostCard`）、`articleExcerptCard`（现 `_FollowingArticleCard`）、`homepageSummaryCard`（现 `_HomeDiscoverableTargetCard`）。
- Writer 是 recommendation 建窗；content hydration 不得改写、不得按媒体补全。未知 recipe → 该项 skip + 观测，禁止 media sniffing。

<a id="req-005"></a>
### REQ-005 列表信封自描述：objectKind + contentType + presentationRecipe + openSurface

- 每个字段一个概念，端一次只读一个字段做一件事：
  - `objectKind: ListObjectKind`（`post` | `entityHomepage`）选投影。
  - `contentType?: ContentType` 做筛选/媒体槽。
  - `presentationRecipe?: FeedPresentationRecipe` 选首页卡。
  - `openSurface: ContentUiSurface` 导航。
- 信封没有 `columns` / `wideLayout`；当前页面身份来自路由上的 `ContentUiSurface`，列数由该面布局策略用视口计算。
- 禁止 `if type==X && recipe==Y` 再推出第三种语义。

<a id="req-006"></a>
### REQ-006 端云解耦：生成闭集能力协商 + 云过滤，禁止默认猜测

- 正常 App 每次列表/推荐请求必须上送与编译期真实支持能力同源生成的 `ClientContentPresentationContract`，禁止手写能力数组或按版本维护第二张能力表。
- 服务端只在整份声明缺席时使用 canonical 契约显式固定并生成的最小能力集合；该集合不随枚举扩展而自动扩大，不代表放行全部能力，也不是对无声明商用旧包的兼容承诺。声明存在但结构非法、集合无效、缺少摘要或摘要伪造时必须拒绝，不得走缺声明默认。
- 服务端按同一 canonical 规则重算并核验有效能力摘要；Go、Python、Dart 对同一有效集合的规范化字节与摘要必须一致，序列化差异不得产生另一窗口身份。
- 云在建窗/hydrate 之前过滤闭集外候选，在声明预算内候选足够时补足页；候选耗尽与预算耗尽必须有可区分终态，不能无界扫描或把预算耗尽显示为没有内容。窗口、cursor、交付页与 App 查询快照绑定同一有效摘要；不同摘要不得复用，回翻不因补位重排已交付页。
- 列表项逐条解码：未知枚举落入显式未知成员，丢掉这一项并打点 `client_contract_skew`，整页继续；文案不得说「内容已删除」。
- 深链 / GetPost 不能省略：typed 终态（需升级）+ 返回。
- 禁止默认展示方式：旧端只渲染自己闭集里、且 wire 已写明的 recipe/surface；把未知类型画成封面卡等于再做一次 `micro → note`。
- 首页 recipe 允许契约声明同一 Surface 内的兼容替换（仅 `homeFeed`）：例如 `inlinePlayer.compatibleRecipe=coverMediaCard`，云选一个旧端闭集内的值写进 wire，这是服务端赋值，不是端侧 fallback。
- 禁止把 `openSurface` 换成另一个面来迁就旧端；目的面没有兼容替换，旧端直接不下发该项。

<a id="req-007"></a>
### REQ-007 全栈残留清册：同一变更闭包删除，禁止双读

- 契约与元数据：`ContentType.micro`、`ContentIdentity`、Post `contentIdentity`、整条 `PromotePostToWork`、`micro_post.yaml`、publication_policy 的 micro 形态确认、事件「点滴升级作品」、feed category → micro、GraphQL 切片含 micro、推荐/曝光 `contentType: string`、objectKind string、搜索 `SearchContentTypeFilter.micro`。
- 服务：`canonicalImportedContentIdentity`、导入强制 work、`PromotePostToWork` 与 `:promoteToWork`、推荐字符串 MAP、product-ops `contentIdentityOutcome`。
- App：`identity`/`displayFormat`/`isArticleLike`、手写 `ContentTypeConstants`、`CreateContentIdentity`、`ContentSurfaceKind.micro`、发布确认点滴/作品、分享按 identity、埋点 identity 冒充 type、主页 `displayFormat==note`、`source` 字符串、l10n 微趣/点滴、生成 category policy。
- Data / 深链 / 规格：producer 不得写入退役身份；深链与旅程不得将退役类型视为有效目标；圈子/搜索/评论/举报的成功夹具使用 canonical 三类 Post，拒绝退役值的负例可保留。
- 反向门：生产代码与 contracts 中作为标识符的 `micro`/`moment`/`contentIdentity`/`displayFormat`/`PromotePostToWork` fail-closed（散文与无关 note 排版除外）。

## 6. 契约与依赖

- 上游能力：[`discovery-content`](../spec.md) 声明的领域入口。
- 下游能力：本目录直接 Story 及其公开结果。
- 一致性要求：遵循本层或父 L1 DEC 声明的一致性边界。

## 7. 集成验收

<a id="sit-001"></a>
### SIT-001 对象 × Surface × 布局 × 配方四层正交模型

- GIVEN 执行"对象 × Surface × 布局 × 配方四层正交模型"所需的身份、输入与上游事实均有效。
- WHEN 参与者发起"对象 × Surface × 布局 × 配方四层正交模型"对应动作。
- THEN `ContentType` 三类、`ContentUiSurface` 五面、`SurfaceLayoutPolicy` 布局矩阵、`FeedPresentationRecipe` 三种卡片家族均为类型化闭集，列表信封每字段单责，端侧禁止多字段交叉推导第三概念。
- AND 失败终态可区分且不产生伪成功事实。

<a id="sit-002"></a>
### SIT-002 生成闭集能力协商与云过滤

- GIVEN 新旧 App 各自编译闭集不同，列表/推荐请求上送 `ClientContentPresentationContract`。
- WHEN 云建窗时按客户端闭集过滤候选。
- THEN 较小能力闭集的 App 收不到其不支持的 `ContentType` / `ListObjectKind` / `FeedPresentationRecipe` / `ContentUiSurface` 值的项；窗口键含 `contractDigest`，不同代 App 窗口互不复用。
- AND 未知枚举逐条 skip + 打点 `client_contract_skew`，整页继续，不炸页。
- AND 深链未知类型返回 typed 终态（需升级），禁止默认卡片。

<a id="sit-003"></a>
### SIT-003 micro / ContentIdentity 全栈同步退役

- GIVEN `ContentType.micro`、`ContentIdentity`、`PromotePostToWork` 已从契约、服务、App、Data 删除。
- WHEN 反向门扫描生产代码与 contracts。
- THEN 作为标识符的 `micro` / `moment` / `contentIdentity` / `displayFormat` / `PromotePostToWork` fail-closed（散文与无关 note 排版不误伤）。
- AND 存量 `contentType=micro` 已一次性迁移为 `image` / `video` / `article`，迁移冲突或无法分类的 typed fail-closed 不进公开 feed。

## 8. 开放事项

<a id="open-001"></a>
### OPEN-001 对象 × Surface × 布局 × 配方四层正交模型

- 类型：`capability_gap`
- 优先级：`P0`
- 准出影响：`block`
- 影响或价值：App 对生成 Surface、布局策略、首页配方和自描述信封的单轨消费尚缺完整行为证据；独立来源归因不得充当目的面或形成第二份展示面登记表。
- 完成判定：`SIT-001` 的所有结果在同一候选由真实测试绑定；生成 Surface 与布局策略贯通首页、主页和聚焦面，不存在手写过渡登记表、两套布局推导或旧投影兜底。

<a id="open-002"></a>
### OPEN-002 生成闭集能力协商与云过滤

- 类型：`capability_gap`
- 优先级：`P0`
- 准出影响：`block`
- 影响或价值：能力声明在真实请求、服务建窗、公开投影及 App 消费间尚缺贯通证据；缺声明固定最小集合、非法声明拒绝、摘要校验和有界补页也未形成同一候选的完整端云证明。
- 完成判定：`SIT-002` 各结果分别由职责匹配的真实测试绑定；服务侧过滤或摘要测试只证明相应子句，不替代 App 未知项隔离与深链终态。固定最小集合由 canonical 契约显式声明并生成，真实请求按批准的 binding 传递生成能力；同一候选满足 [统一游标声明校验](../feed-orchestration-recommendation/unified-items-cursor/spec.md#gwt-002) 与 [过滤分页边界](../feed-orchestration-recommendation/unified-items-cursor/spec.md#gwt-003) 的摘要隔离与补页要求。
- 依赖：canonical 能力协议、请求绑定和对应 exact breaking report 的批准；最小集合成员由可真实支持的基线确定，不以全部枚举或版本映射代替。

<a id="open-003"></a>
### OPEN-003 micro / ContentIdentity 全栈同步退役

- 类型：`capability_gap`
- 优先级：`P0`
- 准出影响：`block`
- 影响或价值：生产读写、生成物、指标、告警及消费者的退役闭包尚缺零残留证明；存量分类、失败恢复与目标环境迁移缺少批准执行后的 receipt/readback，不能凭静态定义宣称清零。
- 完成判定：`SIT-003` 的反向门与环境迁移结果均有同一候选证据；生成器、运行路径和消费者不恢复退役操作。迁移只处理明确退役值，未知值和权威信息冲突保持阻断；故障注入、重跑与回执失败证明可恢复，再由获批准目标环境的盘点、receipt 和 readback 证明活跃存量清零。
- 依赖：目标环境授权及权威数据盘点；不可改写的 release/审计原件、一次性迁移输入和拒绝退役值的负例按各自边界保留，不作为公开读写兼容通道。
