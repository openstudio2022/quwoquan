# L2 Design：内容展示一致性 (`content-display-consistency`)

> 对应规格：[L2 spec](./spec.md)

> 设计触发原因：“统一文章、圈子流、沉浸式浏览器与作者主页之间的展示和状态交接”需要 `article-display-journey`、`circle-feed-viewer-handoff-contract`、`content-action-intent-contract`、`feed-item-dto-contract`、`photo-display-journey`、`video-display-journey`、`viewer-profile-state-sync-contract` 共享状态 owner、契约或质量边界。

## 1. 背景、目标与非目标

- 设计目标：统一文章、圈子流、沉浸式浏览器与作者主页之间的展示和状态交接。
- 非目标：复制字段 schema、实现任务、测试排列组合或执行历史。

## 2. Story 协作与状态流

- [`article-display-journey`](./article-display-journey/spec.md)：整个卡片为统一热区，点击直接进入文章沉浸式阅读器。
- [`circle-feed-viewer-handoff-contract`](./circle-feed-viewer-handoff-contract/spec.md)：圈子 post 进入 viewer 时必须传入。
- [`content-action-intent-contract`](./content-action-intent-contract/spec.md)：更多操作面板只展示已具备真实结果或安全终态的能力；禁止“功能开发中”假入口。
- [`feed-item-dto-contract`](./feed-item-dto-contract/spec.md)：`generated/content/feed_item_dto.g.dart` 标记 `// Code generated ... DO NOT EDIT.`，禁止手改。
- [`photo-display-journey`](./photo-display-journey/spec.md)：让图片频道、沉浸式浏览器与作者主页使用同一内容身份和互动状态，并在返回时保持上下文。
- [`video-display-journey`](./video-display-journey/spec.md)：首页/视频频道/作品浏览器的同一视频 post 未播放态封面一致，点击后能进入同一 `videoUrl` 的播放态。
- [`viewer-profile-state-sync-contract`](./viewer-profile-state-sync-contract/spec.md)：viewer、profile 与 feed 消费同一 canonical `RelationshipCapabilityView` 关系矩阵。

## 3. 端云与数据流

- 上游能力：[`discovery-content`](../spec.md) 声明的领域入口。
- 下游能力：本目录直接 Story 及其公开结果。
- 一致性要求：遵循本层或父 L1 DEC 声明的一致性边界。

## 4. 关键决策

<a id="dec-001"></a>
### DEC-001 列表、沉浸浏览器与作者主页共享对象身份和互动状态
- 决策：列表、沉浸浏览器与作者主页共享对象身份和互动状态。
- 理由：统一文章、圈子流、沉浸式浏览器与作者主页之间的展示和状态交接。
- 被否决方案：由调用方、页面或脚本复制本层状态并绕过公开契约。
- 约束与影响：实现只能细化对应规格与 canonical contract；冲突时先修正规格或契约。
- 关联要求：`REQ-001`
- 影响 Story：[`article-display-journey`](./article-display-journey/spec.md)、[`circle-feed-viewer-handoff-contract`](./circle-feed-viewer-handoff-contract/spec.md)、[`content-action-intent-contract`](./content-action-intent-contract/spec.md)、[`feed-item-dto-contract`](./feed-item-dto-contract/spec.md)、[`photo-display-journey`](./photo-display-journey/spec.md)、[`video-display-journey`](./video-display-journey/spec.md)、[`viewer-profile-state-sync-contract`](./viewer-profile-state-sync-contract/spec.md)
- 关联验收：`SIT-001`

<a id="dec-002"></a>
### DEC-002 ContentUiSurface 是页面身份闭集，聚焦面与 collection 面对等

- 决策：`ContentUiSurface` v1 闭集固定为 `homeFeed`、`profileWorks`、`mediaImmersive`、`articleReader`、`homepageDetail` 五个页面身份。`mediaImmersive` 与 `articleReader` 是聚焦面，与 `homeFeed` / `profileWorks` 两个 collection 面对等，既不是详情别名，也不是内容类型或内容身份的区分。跳转只发生在 Surface 之间，来源归因使用类型化取值，`'home_feed'` / `'profile'` / `'profile_moment'` 字符串 source 随本决策删除。
- 理由：同一个 Post 会出现在多个面上，面之间的差别是 chrome 与布局，不是对象类型。把侵入式浏览器当成「作品」身份或详情别名，等于把页面身份重新编码进对象字段，正是 `contentIdentity` 与 `displayFormat` 交叉推导的来源。新页面先登记 Surface 再写布局与跳转，闭集才能保持可枚举、可协商。
- 被否决方案：把侵入式浏览器当成内容类型或 `displayFormat` 取值；用详情承接面把 collection 面折叠掉；保留点滴轨与作品轨表达页面差异；把 mine/other 或频道变体拆成新的 Surface 种类。
- 约束与影响：Surface 取值由路由携带，对象自身不记得自己属于哪一个面或哪一列网格。`articleReader` 可与 `mediaImmersive` 共用实现路由，但契约上必须是 typed mode 而不是 `isArticleLike` 布尔推导。新增 Surface 必须同时声明布局策略与允许的跳转边，未登记的面不得出现在 wire 上。
- 关联要求：[`REQ-001`](./spec.md#req-001)、[`REQ-002`](./spec.md#req-002)、[`REQ-004`](./spec.md#req-004)
- 影响 Story：[`article-display-journey`](./article-display-journey/spec.md)、[`photo-display-journey`](./photo-display-journey/spec.md)、[`video-display-journey`](./video-display-journey/spec.md)、[`circle-feed-viewer-handoff-contract`](./circle-feed-viewer-handoff-contract/spec.md)
- 关联验收：[`SIT-001`](./spec.md#sit-001)、[`SIT-002`](./spec.md#sit-002)

<a id="dec-003"></a>
### DEC-003 列数只由 SurfaceLayoutPolicy 按 surface 与 windowSizeClass 求值

- 决策：每个 Surface 在自己的 ui_config 声明 `SurfaceLayoutPolicy`，列数在渲染时由 `(surface, windowSizeClass)` 求值：`homeFeed` compact 1 列、expanded 按可用宽度升至上限 4 列；`profileWorks` compact 2 列、expanded 2–4 列走同一网格函数；`mediaImmersive` 与 `articleReader` 恒为全屏单页；`homepageDetail` 是对象页壳。列数不进 Post 字段、不进列表信封，也不进 `FeedPresentationRecipe`。
- 理由：列数是页面对当前窗口尺寸的函数，与对象类型和推荐结果无关。一旦写进对象或 recipe，云就要为每种视口各发一份值，旧包还会因为收到未知列数而整页解码失败。首页手机单列与主页手机双列是现网已有的产品数字，收口到面策略即可原样保持。
- 被否决方案：把单列或双列登记成 recipe 成员；按 `contentType` 推断列数；让云在 wire 上下发 `columns` / `wideLayout`；首页与主页长期各维护一套 breakpoint 常量。
- 约束与影响：布局策略是端侧编译期事实，旧包用自己编译的策略，因此新增列数或断点不构成 wire 变更，也不需要能力协商。同一张卡在 compact 与 expanded 下只允许改变尺寸与 chrome 家族，不允许改变节点结构或阅读顺序；频道对 `phoneColumns` 的覆盖属于 `homeFeed` 策略内部参数。
- 关联要求：[`REQ-001`](./spec.md#req-001)、[`REQ-003`](./spec.md#req-003)
- 影响 Story：[`feed-item-dto-contract`](./feed-item-dto-contract/spec.md)、[`photo-display-journey`](./photo-display-journey/spec.md)、[`video-display-journey`](./video-display-journey/spec.md)
- 关联验收：[`SIT-001`](./spec.md#sit-001)

## 5. 失败与恢复

- 失败类型：权限拒绝、依赖超时、版本冲突或持久化失败。
- 可见结果：调用方收到可区分的 canonical failure 或规格明确允许的降级结果；任何失败均不写入成功事实。
- 恢复动作：调用方按 canonical recovery action 重试、刷新或停止；不得自行合成成功结果。
- 禁止 fallback：不得回退到 Mock、旧 wire、双读双写或页面本地写副本。

## 6. 质量与观测

- 无法优雅承接 outbox 与系统级配置。
- 本地默认值来自 codebase，远端配置只做覆盖。
- `GetAppConfig` 扩展 `client_state_sync` 配置输出结构。
- feature flag、观测、SLO 验证与回滚。
