# Tasks: chat-detail-avatar-display — 对话页头像展示与用户信息缓存

## Phase A — 缓存基础设施

- [ ] A1: 新建 `UserProfileCacheEntry` 数据类 + Hive TypeAdapter（`lib/cloud/chat/cache/user_profile_cache_entry.dart`）→ A5
- [ ] A2: 新建 `UserProfileCacheService`（`lib/cloud/chat/cache/user_profile_cache_service.dart`），内存 LRU(200) + 磁盘 Hive Box → A4~A5
- [ ] A3: 在 `app_providers.dart` 注册 `userProfileCacheServiceProvider` → A4

## Phase B — 同步引擎

- [ ] B1: `UserRepository` 或新建 `UserProfileRepository` abstract 新增 `batchGetTimestamps(userIds)` 和 `batchGetProfiles(ids)` → A6
- [ ] B2: Mock / Remote 实现 → A6
- [ ] B3: 新建 `UserProfileSyncService`（`lib/cloud/chat/cache/user_profile_sync_service.dart`），时间戳比对 + 冷却时间 + 按需拉取 → A6~A7

## Phase C — 对话页 UI 集成

- [ ] C1: `ChatDetailPage` AppBar 增加对方用户头像（`RoundedSquareAvatar` size=36）+ 昵称 → A1
- [ ] C2: `ChatMessageBubble` 非自己消息旁增加 `RoundedSquareAvatar`（size=40）→ A2
- [ ] C3: 头像点击跳转用户主页，传递 userId → A3
- [ ] C4: 进入对话时触发 `UserProfileSyncService.refreshIfNeeded()` → A6
- [ ] C5: 后台刷新失败静默忽略 → A8

## Phase D — 设置页头像尺寸

- [ ] D1: `ChatSettingsPage._MemberAvatar` 使用 `RoundedSquareAvatar`（size=52）→ A9

## Phase E — WebSocket 集成

- [ ] E1: 监听 `user.profile.updated` 事件，更新缓存 → A6

## Phase F — 测试

- [ ] F1: T2 — UserProfileCacheService 单元测试（LRU 淘汰 + 磁盘持久化）
- [ ] F2: T2 — UserProfileSyncService 时间戳比对 + 冷却时间测试
- [ ] F3: T2 — AppBar 头像 Widget test
- [ ] F4: T1 — `/users/timestamps` 契约测试
- [ ] F5: `make gate`
