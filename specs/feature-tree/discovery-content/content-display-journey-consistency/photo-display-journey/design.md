# photo-display-journey 设计

## 设计动因

美图频道与图片浏览器各自拉取数据、index 传递错误、关注/赞/收藏未跨页面共享。本特性建立单一数据源与统一状态管理，保证列表、浏览器、作者详情同源且状态可回传、可重入保持。

## 关键决策

- **DiscoveryFeedProvider**：按 category=photo 管理 feed（items + cursor）
- **路由传参**：图片 MediaViewerPage 通过 route.extra 接收 posts + initialIndex
- **状态**：HomeState（likedPosts、savedPosts、followingUsers）跨页面共享
- **滑动**：PageView itemCount = posts.length；滑动到底 appendNextPage
- **多图**：post 内多图保持顺序，与 post.images 一致

## DTO 集成（D19/D20）

依赖 `feed-item-dto-contract` 完成后：

- 美图列表卡片从 `Map<String, dynamic>` 改为接收 `FeedItemDto`；字段读取方式从 `post['avatarUrl']` 改为 `dto.avatarUrl`
- `ImmersiveImageViewer` 构造参数从多个离散 `String` 参数（`username`、`avatarUrl`、`displayName` 等）改为单个 `FeedItemDto dto`，内部通过 `dto.xxx` 访问
- 这样 `ImmersiveImageViewer` 的参数列表从 20+ 参数降到核心几个（`dto`、`posts`、`initialIndex`）

## Intent 集成（D21/D22/D23）

依赖 `content-action-intent-contract` 完成后：

- `ImmersiveImageViewer` 内部通过 `ref.read(contentIntentProvider).like/save(dto.id)` 处理赞/收藏，`onLikeClick`/`onSaveClick` callback 删除
- `ImmersiveImageViewer` 内部通过 `ref.read(userIntentProvider).follow/unfollow(dto.authorId)` 处理关注，`onFollowClick` callback 删除
- `discovery_page.dart` 不再需要传递三个 callback，组件耦合度大幅降低

## 列表状态与缓存

- **返回不刷新**：从图片浏览返回后，美图列表复用 discoveryFeedProvider 已有数据，不重新请求；若在浏览中已 appendNextPage，列表直接展示扩展后的 feed。
- **图片缓存建议**：列表缩略图使用 CachedNetworkImage（内存+磁盘）；可配置 cacheManager 的 maxNrOfCacheObjects / stalePeriod（业界常用 7～30 天）；浏览器内可对当前帖前后各 1～2 张做预加载，减少滑动白屏。
