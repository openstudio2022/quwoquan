# 开发任务：content-action-intent-contract

## 当前交付任务

### metadata（M）

- [ ] M1：确认 `follow_edge/service.yaml` 中 `FollowUser`（POST `/v1/user/follow/{targetUserId}`）和 `UnfollowUser`（DELETE `/v1/user/follow/{targetUserId}`）路由已存在（✅ 已验证存在），**无需新增**；确认 `UserRepository` 的 Remote 实现使用此路径
- [ ] M2：确认 `post/service.yaml` 中 `LikePost`（POST `/v1/content/posts/{postId}/like`）、`UnlikePost`（DELETE）、`FavoritePost`（POST `/v1/content/posts/{postId}/favorite`）、`UnfavoritePost`（DELETE）路由已存在（✅ 已添加），无需再修改
- [ ] M3：`make verify`（metadata 内部一致性通过）

---

### codegen（C）

- [ ] C1：`make codegen`（如 metadata 变更影响端侧生成产物，执行 `make codegen-app`）

---

### 业务逻辑（A）

- [ ] A1：新建 `lib/core/providers/content_intent.dart`（`ContentIntentNotifier`）
  - `like(String postId)`：乐观更新 `HomeState.likedPosts` → `ContentRepository.likePost(postId)`（调用 `POST /v1/content/posts/{postId}/like`），失败回滚
  - `unlike(String postId)`：乐观更新 → `ContentRepository.unlikePost(postId)`（`DELETE /v1/content/posts/{postId}/like`），失败回滚
  - `save(String postId)`：乐观更新 `HomeState.savedPosts` → `ContentRepository.favoritePost(postId)`（`POST /v1/content/posts/{postId}/favorite`），失败回滚
  - `unsave(String postId)`：乐观更新 → `ContentRepository.unfavoritePost(postId)`，失败回滚
- [ ] A2：新建 `lib/core/providers/user_intent.dart`（`UserIntentNotifier`）
  - `follow(String userId)`：乐观更新 `HomeState.followingUsers` → `UserRepository.followUser(userId)`（调用 `POST /v1/user/follow/{targetUserId}`），失败回滚
  - `unfollow(String userId)`：乐观更新 → `UserRepository.unfollowUser(userId)`（`DELETE /v1/user/follow/{targetUserId}`），失败回滚
- [ ] A3：`ContentRepository` Abstract 接口增加 `likePost` / `unlikePost` / `favoritePost` / `unfavoritePost` 方法签名
- [ ] A4：`MockContentRepository` 实现四个方法（更新本地计数/状态，不发 HTTP）
- [ ] A5：`RemoteContentRepository` 实现四个方法（调用 `CloudRuntimeConfig.gatewayBaseUrl` + 对应路径，使用 `CloudRequestHeaders.forPage`）
- [ ] A6：`UserRepository` Abstract 接口增加 `followUser(String targetUserId)` / `unfollowUser(String targetUserId)` 方法签名
- [ ] A7：`MockUserRepository.followUser/unfollowUser` 实现（更新本地 mock following set，不发 HTTP）
- [ ] A8：`RemoteUserRepository.followUser/unfollowUser` 实现（调用 `POST/DELETE /v1/user/follow/{targetUserId}`，使用 `CloudRuntimeConfig` + `CloudRequestHeaders`）
- [ ] A9：新建 `lib/core/providers/intent_providers.dart`，注册：
  - `contentIntentProvider = NotifierProvider<ContentIntentNotifier, void>`
  - `userIntentProvider = NotifierProvider<UserIntentNotifier, void>`

---

### 测试（T）

- [ ] T1：Intent 单元测试（`test/content/content_intent_test.dart`）
  - 场景 1：`like(postId)` → `HomeState.likedPosts` 立即包含 `postId`（乐观）
  - 场景 2：`like(postId)` + 模拟 `ContentRepository.likePost` 失败 → `HomeState.likedPosts` 回滚
  - 场景 3：`follow(userId)` → `HomeState.followingUsers` 立即包含 `userId`（乐观）
  - 场景 4：`follow(userId)` + 模拟 `UserRepository.followUser` 失败 → 回滚
- [ ] T2：`make gate` 通过（metadata 一致性 + 结构约束）

---

## 搁置任务（带规划）

| 任务 | 搁置原因 | 计划重启条件 |
|------|----------|-------------|
| Intent 操作幂等性（debounce） | 当前规模无需 | 出现重复点赞 bug 时启用 300ms debounce |
| 操作日志上报（BehaviorRepository） | 依赖 behavior analytics 系统就绪 | analytics pipeline 完成后，Intent 内追加 `BehaviorRepository.track` 调用 |

---

## 未来演进任务

- `CircleIntentNotifier`（圈子关注）：复用 `UserIntentNotifier` 模式，新增 `circle_intent.dart`
- Intent 重试策略：网络抖动时内部 retry（1次），减少回滚频率
- 云侧反馈同步：like/save API 返回最新计数时，更新 `FeedItemDto` 对应字段
