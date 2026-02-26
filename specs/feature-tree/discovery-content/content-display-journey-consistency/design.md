# content-display-journey-consistency 设计

## 设计动因

当前发现页列表与图片/视频浏览器各自拉取数据、index 传递错误、关注/赞/收藏状态未在跨页面共享，导致用户旅程中数据与状态不一致。本设计建立单一数据源与统一状态管理，保证列表、浏览器、作者详情三者同源且状态可回传、可重入保持。

## 适用场景与约束

- **适用**：发现页美图/视频频道，沉浸式图片/视频浏览器，作者详情页
- **约束**：依赖 ContentRepository、HomeState（或等效 Provider）、BehaviorRepository；须支持 appDataSourceModeProvider 切换 Mock/Remote
- **局限性**：微趣、文章暂不纳入；作者详情的其他能力（如作品列表）沿用现有实现

## 关键决策

### 1. 单一数据源：DiscoveryFeedProvider

- **方案**：新建 Provider 管理 feed（items + nextCursor），供 DiscoveryPage 与 MediaViewerPage 共用
- **来源**：ContentRepository.listDiscoveryFeedPage（支持 cursor 分页）
- **存储**：按 category（photo/video/article/moment）分别管理，四类独立旅程互不混用

### 2. 路由传参：posts + initialIndex

- **方案**：MediaViewerPage 通过 route.extra 接收 `(posts, initialIndex)` 或 `(feedKey, initialIndex)`；不再自拉数据
- **index 传递**：美图/视频卡片点击时传入 itemBuilder 的 index，不再固定为 0

### 3. 状态管理：HomeState 跨页面共享

- **方案**：关注、赞、收藏统一使用 homeStateProvider（likedPosts、savedPosts、followingUsers）
- **注入**：MediaViewerPage、AuthorProfile 均从 ref.watch(homeStateProvider) 读取并更新
- **重入**：HomeState 在 App 生命周期内持久，退出再进保持一致；若需跨进程持久化，可后续接云侧 API

### 4. 作者详情关注回传

- **方案**：AuthorProfile 关注/取消后通过 context.pop(result: followState) 或 Provider 通知；MediaViewerPage 监听并刷新当前 post 的 following 展示
- **备选**：若 AuthorProfile 与 MediaViewer 共用 followingUsers Provider，无需显式 pop 回传，状态自动同步

### 5. 滑动顺序与加载更多

- **方案**：浏览器 PageView 的 itemCount = posts.length；滑动到底触发 appendNextPage(cursor)，追加到 feed 并刷新
- **顺序**：与列表完全一致，因共用同一 feed

### 6. 四类内容独立旅程

- **图片**：美图频道 → 图片浏览器 → 作者详情；category=photo；**优先实现**
- **视频**：视频频道 → 视频浏览器 → 作者详情；category=video；独立实现
- **文章**：文章频道 → 文章详情页 → 作者详情；category=article；独立实现
- **微趣**：微趣频道 → 微趣详情/浏览器 → 作者详情；category=moment；独立实现

每类旅程复用相同模式（单一数据源、状态注入、路由传参），但数据源与 Provider 按 category 隔离，互不混用。

### 7. FeedItemDto 规范字段层（feed-item-dto-contract）

- **方案**：由 `_projections/discovery_feed.yaml` 的 `client_projection.fields` codegen 生成 `FeedItemDto`（DO NOT EDIT）
- **Repository 出口统一**：`MockContentRepository` / `RemoteContentRepository` 均输出 `FeedItemDto`，不再返回 `Map<String, dynamic>`
- **alias resolver 内置**：`FeedItemDto.fromMap` 处理 `likes`/`likesCount`/`likeCount` 等别名，UI 层无需任何兜底逻辑
- **`generated/` 按域组织**：`cloud/runtime/generated/content/` 子目录，与 `cloud/services/content/` 对称

### 8. 操作意图层（content-action-intent-contract）

- **方案**：`ContentIntentNotifier`（like/save）+ `UserIntentNotifier`（follow/unfollow），Riverpod AsyncNotifier
- **乐观更新**：操作发生 → 立即更新 `HomeState`（UI 无延迟）→ 异步发 API → 失败回滚快照
- **ImmersiveImageViewer 去回调**：删除 `onLikeClick`/`onSaveClick`/`onFollowClick` 三个 callback，改为内部 `ref.read(contentIntentProvider).like(dto.id)` 直接调用

## 数据流（目标态）

```
_projections/discovery_feed.yaml
    │ make codegen-app
    ▼
FeedItemDto (cloud/runtime/generated/content/feed_item_dto.g.dart)
    │
    ▼
ContentRepository (Mock/Remote) ─── List<FeedItemDto>
    │
    ▼
DiscoveryFeedProvider (List<FeedItemDto>)
    │
    ├── DiscoveryPage (美图/视频列表)  ──► dto.avatarUrl, dto.likeCount ...
    │           │ 点击 post, index
    │           ▼
    └── MediaViewerPage (FeedItemDto[] + initialIndex)
                │
                ├── ImmersiveImageViewer (dto: FeedItemDto)
                │       │ 赞/收藏
                │       ▼
                │   contentIntentProvider.like/save(dto.id) ──► HomeState (乐观) ──► ContentRepository API
                │       │ 关注
                │       ▼
                │   userIntentProvider.follow(dto.authorId) ──► HomeState (乐观) ──► UserRepository.followUser
                │
                └── 作者头像 ──► AuthorProfile (同源 post/author)
                                    │ 关注/取消（共享 homeStateProvider）
                                    └── 无需 pop 回传，状态自动同步
```

## 未来演进

- **跨进程状态持久化**：当前 HomeState 仅进程内；若需冷启动后保持，可接 GetReactionState、UserRepository.following 等云侧 API
- **视频、文章、微趣**：各自独立特性（video/article/moment-display-journey），复用 FeedItemDto + Intent 层模式，按 category 分支处理差异字段
- **圈子流**：若圈子流也需浏览器一致性，可抽象通用 `FeedViewerJourneyProvider` 或新增 L3
- **FeedItemDto → ViewModel**：当需要 UI 计算字段（`timeAgoText` 等）时，在 DTO 基础上包装 ViewModel，DTO 保持 DO NOT EDIT
