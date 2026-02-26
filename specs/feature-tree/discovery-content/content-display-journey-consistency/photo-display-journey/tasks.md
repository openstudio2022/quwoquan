# 开发任务：photo-display-journey

## 当前交付任务

### 单一数据源（已完成）

- [x] D1：建立 DiscoveryFeedProvider，category=photo 管理美图 feed
- [x] D2：路由改造，图片 MediaViewerPage 从 route.extra 接收 posts + initialIndex
- [x] D3：美图卡片点击传入真实 index
- [x] D4：作者详情同源（从 feed 或 getPost）
- [x] D12：图片浏览器滑动顺序 = 美图频道 feed 顺序
- [x] D13：多图 post 内滑动
- [x] D14：滑动到底加载更多

---

### DTO 集成（依赖 feed-item-dto-contract 类型化 DTO 拆分完成后执行）

- [ ] D19：美图频道卡片改用 `PhotoPostDto` 字段（`dto.avatarUrl`、`dto.displayName`、`dto.likeCount`、`dto.width`、`dto.height` 等），删除旧 `Map<String, dynamic>` 取值；`aspectRatio` 直接由 `dto.width / dto.height` 计算，不再从 Map 读取
- [ ] D20：`ImmersiveImageViewer` 构造函数参数改为接收 `PhotoPostDto`（取代原来分散的 `username`、`avatarUrl`、`displayName`、`backgroundUrl` 等离散参数），内部直接读 `dto.xxxx`
- [ ] D24：`lib/ui/discovery/widgets/photo_feed_grid.dart` 新建（从 `discovery_page.dart` 抽取美图 Tab 渲染逻辑，接收 `List<PhotoPostDto>`），`discovery_page.dart` 引用此 Widget（目录迁移 R2 完成后执行）

---

### 状态同步与重入（依赖 feed-item-dto-contract 完成后执行）

- [ ] D5：浏览器注入 followingUsers（从 `homeStateProvider` 读取 `followingUsers`，展示关注/已关注态）
- [ ] D6：浏览器注入赞/收藏状态（从 `homeStateProvider.likedPosts`/`savedPosts` 读取，展示当前 post 的已赞/已收藏态）
- [ ] D9：作者详情关注/取消 → 返回浏览器自动同步（因共用 `homeStateProvider`，无需显式 pop 回传）
- [ ] D10：全链路使用 HomeState（列表、浏览器、作者详情三处均从 `homeStateProvider` 读写，无局部独立状态）
- [ ] D11：退出再进状态保持（HomeState 在 App 进程内持久，provider 不 dispose）

---

### Intent 集成（依赖 content-action-intent-contract 完成后执行）

- [ ] D21：`ImmersiveImageViewer` 点赞 → `ref.read(contentIntentProvider).like(dto.id)`，删除 `onLikeClick` callback
- [ ] D22：`ImmersiveImageViewer` 收藏 → `ref.read(contentIntentProvider).save(dto.id)`，删除 `onSaveClick` callback
- [ ] D23：`ImmersiveImageViewer` 关注/取消关注 → `ref.read(userIntentProvider).follow/unfollow(dto.authorId)`，删除 `onFollowClick` callback

> ⚠️ D21~D23 入口路径迁移后应位于 `lib/ui/discovery/pages/discovery_page.dart`，不再是 `features/home/pages/`

---

### Mock/Remote 切换

- [ ] D17：Settings 页面增加 Mock/Remote 切换入口（`AppDataSourceMode` 切换，现有 Developer Settings 页面增加开关）
- [ ] D18：切换为 Remote 后图片旅程全链路正确（`RemoteContentRepository` 拉取真实 feed，`FeedItemDto.fromMap` 解析响应）

---

## 搁置任务（带规划）

| 任务 | 搁置原因 | 计划重启条件 |
|------|----------|-------------|
| 跨进程状态持久化（冷启动后保持关注/赞/收藏） | 依赖云侧 GetReactionState、UserRepository.followStatus API | content-action-intent-contract + 云侧 API 完整后，HomeState 初始化时拉取用户状态 |
| 图片缓存 CachedNetworkImage 精调（stallPeriod/maxNrOfCacheObjects） | 非 MVP 功能 | 性能优化阶段 |

---

## 未来演进任务

- 视频旅程（video-display-journey）：复用本 L3 模式，Category=video 独立实现
- 评论数、转发数实时拉取（当前用 post 快照）：需 ContentRepository 新增 getPostStats API
