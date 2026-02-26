# L3 特性：content-action-intent-contract（内容操作意图契约）

## 功能说明

为内容交互操作（赞、收藏）和用户关系操作（关注/取消关注）建立统一的**意图契约层**：点击即时乐观更新本地状态，同时异步触发云侧 API 回写，失败自动回滚。替换当前散落在各组件的 `onLikeClick`/`onSaveClick`/`onFollowClick` 回调链。

## 职责边界

- **负责**：
  - `lib/domain/content/content_intent.dart`（`ContentIntentNotifier`：`like(postId)` / `save(postId)`，乐观更新 + 回滚）
  - `lib/domain/user/user_intent.dart`（`UserIntentNotifier`：`follow(userId)` / `unfollow(userId)`，乐观更新 + 回滚）
  - `UserRepository` Abstract + Mock + Remote 补全 `followUser` / `unfollowUser` API
  - `lib/core/providers/intent_providers.dart` 注册 `contentIntentProvider`、`userIntentProvider`
  - `follow_edge/service.yaml` 已有 FollowUser/UnfollowUser 路由（`POST/DELETE /v1/user/follow/{targetUserId}`），无需新增
- **不负责**：DTO 读操作规范化——由 `feed-item-dto-contract` 负责；具体 UI 组件回调删除——由 `photo-display-journey` D21~D23 负责

## 适用范围与约束

- **适用**：`content-display-journey-consistency` 所有媒体类型的互动操作（赞/收藏/关注）
- **前置条件**：`follow_edge/service.yaml`（FollowUser/UnfollowUser，已存在）和 `post/service.yaml`（LikePost/UnlikePost/FavoritePost/UnfavoritePost，已补充）路由均已定义；`UserRepository`/`ContentRepository` 接口已存在
- **不适用**：评论发送（有独立 `comment_system` 组件）；圈子关注（另见 circle-community L1）
- **约束**：
  - Intent 必须通过 Provider 注入，禁止 Feature 直接实例化 `ContentIntentNotifier`
  - 乐观更新必须有回滚：云侧返回 4xx/5xx 时还原 `HomeState`
  - `user_profile/service.yaml` 路由变更须先 `make verify` 再 codegen

## 与父/子节点关系

| 节点 | 关系 |
|------|------|
| `content-display-journey-consistency`（L2） | 父节点 |
| `feed-item-dto-contract`（L3） | 并列；本 L3 依赖 `FeedItemDto.id`/`authorId` 字段（需 DTO 先完成） |
| `photo-display-journey`（L3） | 依赖本 L3 提供的 `contentIntentProvider`/`userIntentProvider`（D21~D23） |
| `video/article/moment-display-journey`（L3） | 后续依赖，复用 Intent 层 |

## 验收标准概要

- A1：`user_profile/service.yaml` 含 FollowUser/UnfollowUser 路由，`make verify` 通过
- A2：`UserRepository`（Abstract/Mock/Remote）均实现 `followUser` / `unfollowUser`
- A3：`ContentIntentNotifier.like/save` 触发乐观更新，`HomeState` 立即反映（无需等待 API 返回）
- A4：`UserIntentNotifier.follow/unfollow` 触发乐观更新
- A5：云侧 API 失败时 `HomeState` 回滚到操作前状态
- A6：`contentIntentProvider`/`userIntentProvider` 已在 `intent_providers.dart` 注册
- A7：Intent 单元测试覆盖乐观更新 + 回滚场景，`make gate` 通过
