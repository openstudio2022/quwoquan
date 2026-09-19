# L2 Business Capability：内容展示一致性 (`content-display-consistency`)

> 所属领域：[`discovery-content`](../spec.md)
>
> 设计引用：[本层 design.md](./design.md)

## 1. 能力目标

统一 Surface 闭集、跳转边、布局矩阵，删除 moment 旅程；确保同一 Post 在 `homeFeed`、`profileWorks`、`mediaImmersive`、`articleReader` 四面保持身份、互动状态与上下文一致。

## 2. 范围与非目标

### In Scope

- Surface 闭集（`homeFeed` / `profileWorks` / `mediaImmersive` / `articleReader` / `homepageDetail`）与跳转边类型化。
- 布局矩阵：首页 compact 1 列 / PC 多列，主页 compact 2 列 / PC 多列，侵入式全屏，禁止按 `contentType` 推断列数。
- 删除 `moment-display-journey` 旅程规格与 `micro` 展示路径残留。
- 文章、圈子流、沉浸式浏览器与作者主页之间的展示和状态交接。
- 全入口 typed 意图、同 verified actor 私有状态、durable pending/unknown 恢复，以及正文、本人态和统计的分层展示与有界刷新。
- Post 收藏不回归；实体「想去」保持现役 owner，本次不增加想去功能。

### Out of Scope

- 其他 L2 的事实所有权、metadata schema 与实现施工步骤。

## 3. Journey / Scenario 贡献

- [`JNY-003 / SCN-007`](../../spec.md#scn-007)
  - 本能力接收：该 Scenario 进入本能力边界的已授权主体与 canonical 输入。
  - 本能力处理：统一 Surface 闭集、跳转边与布局矩阵，删除 moment 旅程；同一 Post 跨面保持身份、互动状态与上下文一致。
  - 本能力输出：直属 Story 组合产生的可观察结果与明确失败终态。
  - 失败时终态：保留已确认事实，并返回可恢复的 canonical failure。

## 4. Story



- [`article-display-journey`](./article-display-journey/spec.md)：整个卡片为统一热区，点击直接进入文章沉浸式阅读器。
- [`circle-feed-viewer-handoff-contract`](./circle-feed-viewer-handoff-contract/spec.md)：圈子 post 进入 viewer 时必须传入。
- [`content-action-intent-contract`](./content-action-intent-contract/spec.md)：更多操作面板只展示已具备真实结果或安全终态的能力；禁止"功能开发中"假入口。
- [`feed-item-dto-contract`](./feed-item-dto-contract/spec.md)：`generated/content/feed_item_dto.g.dart` 标记 `// Code generated ... DO NOT EDIT.`，禁止手改。
- [`photo-display-journey`](./photo-display-journey/spec.md)：让图片频道、沉浸式浏览器与作者主页使用同一内容身份和互动状态，并在返回时保持上下文。
- [`video-display-journey`](./video-display-journey/spec.md)：首页/视频频道/作品浏览器的同一视频 post 未播放态封面一致，点击后能进入同一 `videoUrl` 的播放态。
- [`viewer-profile-state-sync-contract`](./viewer-profile-state-sync-contract/spec.md)：viewer、profile 与 feed 消费同一 canonical `RelationshipCapabilityView` 关系矩阵。

注：`moment-display-journey`（微趣旅程）不再是本能力的 Story，其行为基线由 `mediaImmersive` Surface 统一承担。

## 5. 能力要求

<a id="req-001"></a>
### REQ-001 Surface 闭集类型化：五面对齐现网页面，禁止字符串 source

- `ContentUiSurface` v1 闭集：
  - `homeFeed`：首页内容流（频道变体不是新 Surface 种类）。
  - `profileWorks`：我的/他人主页「记录」作品格（mine/other 是 viewer 模式，不是两种 Surface）。
  - `mediaImmersive`：侵入式媒体浏览器（现 `WorksImmersiveViewer` / `workBrowser`）。
  - `articleReader`：文章沉浸阅读（可与 `mediaImmersive` 共用路由、typed mode；对外仍是独立 Surface 语义）。
  - `homepageDetail`：实体主页详情。
- `searchResults` / `circleHubFeed` 不在 v1 闭集内：新页面先登记 Surface，再写布局与跳转。
- 删除 `'home_feed'` / `'profile'` / `'profile_moment'` 字符串 source 冒充 Surface。
- 本能力必须组合直属 Story 与公开契约，交付“统一文章、圈子流、沉浸式浏览器与作者主页之间的展示和状态交接”所定义的业务结果；失败终态必须可区分且不得伪造成功。
- [状态同步](./viewer-profile-state-sync-contract/spec.md#req-003) 拥有同 actor 分区、逐对象 hydrate、persist 成功、singleflight/epoch 与 unknown 恢复的展示结果；[动作意图](./content-action-intent-contract/spec.md#req-003) 拥有全部现役入口的 typed coordinator/metadata surface 绑定；[视频旅程](./video-display-journey/spec.md#req-006) 验证模式往返不丢上述事实。
- 关注云确认、点赞按钮乐观与统计新鲜度各自可观察；公共内容、本人互动、命令投递和统计分层，不把无命令读失败画成 pending。REST 与公共 GraphQL 加私有互动组合均保持受信 actor 边界。
- 源绝对期限与有界可见刷新组合交付跨设备收敛；5 秒前台新鲜度仍需批准容量下端到端实测，不由某个 reader/缓存成功推出。

<a id="req-002"></a>
### REQ-002 跳转边类型化：Surface 之间，不是类型推导

- 跳转图（Surface 间导航，对象自身不记得自己属于哪一列网格）：
  - `(homeFeed | profileWorks) + post.image|video` → `mediaImmersive`
  - `(homeFeed | profileWorks) + post.article` → `articleReader`
  - `homeFeed + entityHomepage` → `homepageDetail`
  - 实体主页不进入 `mediaImmersive`
- 沉浸会话保留打开它的列表上下文、对象序位与返回锚点；这些上下文不得改变内容身份或目的面。
- 来源归因只消费既有内容行为契约的 `ReferralSource`；当前页面布局使用 `ContentUiSurface`，目的导航使用云端物化的 `openSurface`，三者互不代偿。圈子与搜索来源不得伪装成首页 Surface，也不得由内容类型或媒体附件推导。

<a id="req-003"></a>
### REQ-003 布局矩阵固定：页面 × 视口，不按 contentType 推断列数

- v1 布局矩阵（冻结进各 Surface 的 ui_config，不进 Post）：
  - `homeFeed` × compact：1 列（频道可覆盖 `phoneColumns`，关注保持 1）。
  - `homeFeed` × expanded/PC：按可用宽度升到 N 列（上限 4）。
  - `profileWorks` × compact：2 列。
  - `profileWorks` × expanded/PC：2–4 列同一网格函数。
  - `mediaImmersive` / `articleReader`：1，全屏，与窗口列数无关。
  - `homepageDetail`：对象页壳，不是 post 网格。
- 同一张首页富卡在 compact 是单列、在 PC 是窄列；主页用另一套预览格 chrome（现 `_WorksPostCard`）。变的是 Surface 布局与 chrome 家族，不是 `ContentType`。
- 禁止：把「单列/两列」写成 recipe 成员；按 `contentType` 推断列数；首页与主页两套 breakpoint 长期分叉。

<a id="req-004"></a>
### REQ-004 删除 moment 旅程与 micro 展示路径

- 删除 `moment-display-journey` 规格（旧「行为基线：作品侵入式浏览器作为统一行为基线；微趣点击图片/视频后进入同等交互能力的侵入式浏览器」已被 `mediaImmersive` Surface 统一替代）。
- `mediaImmersive` 是与 `homeFeed` / `profileWorks` 对等的一等 Surface，不是「微趣/作品」内容身份的区分。
- 同一 `Post.contentType=image|video` 从首页或主页点击后进入同一 `mediaImmersive` Surface，不因「点滴/作品」分叉。

<a id="req-005"></a>
### REQ-005 跨面状态一致：同一 Post 保持身份、互动状态与上下文

- 内部用户 canonical key 统一为 `ProfileSubjectId`；post 作者引用统一为 `authorProfileSubjectId`。
- feed、viewer、profile 共用统一 provider 同步关系态与互动状态。
- 图片、视频、文章进入浏览器/阅读器后，标题（可选）和正文（可选）必须与对应 post 展示一致。
- Web 精品不恢复独立「精品队列」hero/rail；当前商用口径为复用发现内容流的宽屏多列墙 + 统一 `workBrowser` 落点。
- Web 内容区复用 `HomeMultiFormFeed` 宽屏多列墙；post 点击统一调用 `openHomeFeedPost(...)`，进入 `AppRoutePaths.workBrowser(...)` 与 `WorksImmersiveViewer`。
- 禁止回退到旧「精品队列」hero/rail、右侧说明 rail 或独立精品壳；建立独立 Web 精品容器前必须先更新本 L2 规格、页面契约和测试。

<a id="req-006"></a>
### REQ-006 alpha/beta/gamma/prod composition 的所有对象级 Query/Command port 只装配 Remote adapter

- typed double 仅存在测试树，代码图、runner 与 UAT support 不得保留 fixture override 或运行时 Mock/Remote 切换。
- 运行时同步参数属于 `sys.*`，不得落到 `ops.*`、业务 feature flag 或 `ui_config.yaml`。

## 6. 契约与依赖

- 上游能力：[`discovery-content`](../spec.md) 声明的领域入口。
- 下游能力：本目录直接 Story 及其公开结果。
- 一致性要求：遵循本层或父 L1 DEC 声明的一致性边界。

## 7. 集成验收

<a id="sit-001"></a>
### SIT-001 Surface 闭集、跳转边与布局矩阵类型化

- GIVEN 执行"Surface 闭集、跳转边与布局矩阵类型化"所需的身份、输入与上游事实均有效。
- WHEN 参与者发起"Surface 闭集、跳转边与布局矩阵类型化"对应动作。
- THEN `ContentUiSurface` 五面闭集、跳转边、布局矩阵均类型化；字符串 source 删除；侵入式浏览器是一等 Surface。
- AND 同一 Post 在 `homeFeed` compact 1 列、`profileWorks` compact 2 列、`mediaImmersive` 全屏保持身份、互动状态与上下文一致。
- AND 直属 Story 共同交付“统一文章、圈子流、沉浸式浏览器与作者主页之间的展示和状态交接”，失败终态可区分且不产生伪成功事实。
- AND Feed/详情/作者作品/搜索直达/视频各方向/评论入口的同 actor 意图共用 coordinator，surface 与目标合法，切身份和旧网络/磁盘/capability 不覆盖较新确认。
- AND 没有命令的读失败不产生 pending；Post 按钮可乐观但数字只读服务端事实，Comment 三态独立，公共 GraphQL 与私有切片不泄漏 actor，receipt 确认不等待统计。
- AND 引用 `viewer-profile-state-sync-contract` 的 `GWT-002`～`GWT-007`、`content-action-intent-contract` 的 `GWT-002`、`GWT-003` 与 `video-display-journey` 的 `GWT-005`；三层/设备和容量各自取证，缺证据保留最低 Story OPEN。

<a id="sit-002"></a>
### SIT-002 删除 moment 旅程与 micro 展示路径

- GIVEN `moment-display-journey` 规格已删除，`mediaImmersive` Surface 统一替代旧「微趣点击图片/视频后进入侵入式浏览器」行为基线。
- WHEN 同一 `Post.contentType=image|video` 从首页或主页点击。
- THEN 进入同一 `mediaImmersive` Surface，不因「点滴/作品」内容身份分叉。
- AND 规格、路由、UI、测试无 moment 旅程残留。

## 8. 开放事项

<a id="open-001"></a>
### OPEN-001 Surface 闭集、跳转边与布局矩阵类型化

- 类型：`capability_gap`
- 优先级：`P0`
- 准出影响：`block`
- 影响或价值：尚缺同一候选的端云跨面验收。页面身份与布局策略须由 canonical 契约生成并被真实页面消费；来源归因独立复用内容行为契约，不能拿来源枚举代替目的面或布局登记表。
- 当前缺口：正式生成物、首页与个人主页真实约束宽度下的布局消费、云端 `openSurface` 导航、跨面互动状态与返回锚点尚未取得完整同候选证据。局部生成器测试或删除过渡枚举不构成该能力闭环。
- 完成判定：`SIT-001` 对应行为满足且真实测试 `spec_ref` 有效；`ContentUiSurface` 与 `SurfaceLayoutPolicy` 同源生成，首页 compact 1 列、主页 compact 2 列及聚焦全屏由同一策略求值；圈子/搜索/首页/作者主页的 `ReferralSource` 不因目的面或宽度改变；无第二套 Surface/来源登记表。

<a id="open-002"></a>
### OPEN-002 删除 moment 旅程与 micro 展示路径

- 类型：`capability_gap`
- 优先级：`P0`
- 准出影响：`block`
- 影响或价值：`moment-display-journey` 目录已从规格树移除，`contentIdentity` 与 `displayFormat` 派生轴已从 `ContentPostViewData` 删除，点击去向不再因「点滴/作品」内容身份分叉。剩余缺口是侵入式浏览器尚未成为契约意义上的一等 Surface：它仍是 `workBrowser` 路由壳内的形态分支，而不是由云物化的 `openSurface` 单字段导航，`SIT-002` 因此仍无可绑定的真实测试证据。
- 当前缺口：导航边尚未证明只消费云端物化的 `openSurface`；列表项与详情水合必须保留该决策，不能按 `contentType` 重算目的面。既定目的面内按内容类型渲染媒体槽不等同于导航推导，应分别验证。
- 当前缺口：未知目的面尚需逐项隔离与深链升级终态的同候选行为证据，不以字符串扫描数量代替运行验证。
- 完成判定：`SIT-002` 对应行为满足且真实测试 `spec_ref` 有效；`mediaImmersive` / `articleReader` 作为 `openSurface` 取值进入 App 并成为唯一导航依据，端侧不再按 `contentType` 自行选择目的面
