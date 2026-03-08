# 开发任务：moment-display-journey

## 已完成任务（历史）

顺序：metadata → codegen → 业务逻辑 → 测试（本特性为 UI 逻辑，无 metadata 变更）。

### 数据源与 feedPosts

- [x] D1：DiscoveryFeedProvider 增加 category=moment
- [x] D2：发现页微趣卡片点击时传入 feedPosts（moments 列表），`_onPostTap(post, imageIndex, feedPosts: moments, category: 'moment')`
- [x] D3：微趣详情/浏览器从 route.extra（MediaViewerExtra）接收 posts + initialIndex
- [x] D4：作者详情同源

### 媒体浏览器

- [x] D5：ImmersiveImageViewer 增加 layoutMode（flat | nested）
  - flat：保持现有一维 PageView
  - nested：外层 PageView.vertical（微趣）× 内层 PageView.horizontal（同微趣图）
- [x] D6：PhotoDetailPage 在 category=moment 时传入 layoutMode=nested
- [x] D7：微趣图片/视频分流：有 videoUrl → ImmersiveVideoViewer，否则 → ImmersiveImageViewer

### 文字展示

- [x] D8：媒体浏览器底部文字：默认 3 行，超出显示「...全文」；点击展开后可滚动浏览完整内容
- [x] D9：文字数据源使用 post.body

### 状态同步与重入

- [x] D10：微趣浏览器注入 followingUsers、赞/收藏/评论数/转发
- [x] D11：作者详情关注变更返回同步
- [x] D12：全链路 HomeState，重入状态保持
- [x] D13：滑动到底加载更多（onNearEnd 回调）

### 测试

- [x] D14：微趣媒体浏览器 UI 回归：feedPosts、二维导航、文字 3 行+全文展开

## 当前交付任务（`/prd` / `/design` update）

> 目标：统一侵入式浏览器内核，works/moment 分实例装配；顶栏分离；底栏复用作品同源实现。

- [ ] D17：抽取 `ImmersivePostViewerCore`
  - 统一处理分页手势、纯净模式、状态同步、`onNearEnd` 回调
  - 不改变既有业务语义，仅做能力收敛

- [ ] D18：抽取统一底栏 `ImmersiveEngagementBar`（以 works 行为为基线）
  - 从现有 works 底栏抽取为可复用组件
  - 保持动作顺序、计数规则、回调语义不变

- [ ] D19：拆分顶部工具栏为 `WorksTopBar` / `MomentTopBar`
  - `WorksTopBar`：完整信息
  - `MomentTopBar`：仅返回+更多

- [ ] D20：新增 `MomentImmersiveViewer` 场景装配并接入图片/视频详情页
  - 在 `PhotoDetailPage`/`VideoDetailPage` 的 moment 分支接入
  - 保持 `feedPosts`、`initialIndex`、`initialImageIndex` 的链路完整

- [ ] D21：`WorksImmersiveViewer` 迁移至同一 core + engagement 体系
  - works 场景保持现有业务语义与视觉表现
  - 去除重复实现，保留场景装配层职责

- [ ] D22：路由与参数对齐
  - `MomentSocialFeed -> DiscoveryPage._onPostTap` 统一传参
  - 图片/视频入口在侵入式打开时命中正确 post 与媒体索引

- [ ] D23：测试补齐
  - 新增/更新 widget 回归：顶栏差异、底栏一致、二维导航
  - 覆盖 moment 图文与 moment 视频链路

- [ ] D24：本地门禁与结果记录
  - `flutter analyze`
  - 指定 UI 回归测试
  - `make gate`

## 延期验收（deferred，对应 acceptance A2/A3/A6）

- A2 关注/赞/收藏跨页面一致：需 E2E 或 Patrol 回归；重启条件：端到端测试基建就绪
- A3 作者详情关注变更返回同步：需集成测试；重启条件：同上
- A6 Mock/Remote 切换后正确：需 appDataSourceMode 切换 + feed 断言；重启条件：集成/冒烟测试覆盖 Mock/Remote 切换
