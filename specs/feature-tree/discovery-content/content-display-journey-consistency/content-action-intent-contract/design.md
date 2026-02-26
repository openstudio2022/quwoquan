# content-action-intent-contract 设计

## 设计动因

当前互动操作（赞/收藏/关注）存在两个根本问题：

1. **回调链散乱**：`ImmersiveImageViewer` 有三个 callback（`onFollowClick`、`onLikeClick`、`onSaveClick`），由 `discovery_page.dart` 传入，`discovery_page.dart` 再调 `homeState.toggleLike/toggleSave/toggleFollow`，回调层数深且难以溯源。
2. **纯本地状态，无云侧回写**：`HomeState` 的 `toggleLike/toggleSave/toggleFollow` 仅更新本地 Set，不发任何 API 请求，重启 App 后状态丢失，云侧与本地不同步。

本特性引入 Intent 层：点击 → Intent Notifier 立即更新本地 `HomeState`（乐观）→ 异步发 API → 失败回滚。

## 当前态 → 目标态

| 维度 | 当前态 | 目标态 |
|------|--------|--------|
| 互动调用路径 | Widget → callback → `discovery_page._handleLike` → `HomeState.toggleLike` | Widget → `ref.read(contentIntentProvider).like(postId)` |
| 云侧回写 | 无 | `ContentIntentNotifier` 异步调 `ContentRepository.likePost(postId)` |
| 关注 API | `UserRepository` 无 follow/unfollow | `UserRepository` 补全，Mock/Remote 均实现 |
| 失败回滚 | 无（操作即生效，无法撤回） | API 失败 → `HomeState` 回滚到操作前快照 |
| Provider 注册 | 无 intent provider | `intent_providers.dart` 注册，Feature 通过 `ref.read` 访问 |

## 方案对比

### 方案 A（选定）：Riverpod AsyncNotifier + 乐观更新
- `ContentIntentNotifier extends AsyncNotifier`，持有对 `HomeState` 和 `ContentRepository` 的引用
- `like(postId)` 流程：① 快照当前 liked set；② `HomeState.add(liked, postId)`（立即 UI 更新）；③ `await ContentRepository.likePost(postId)`；④ 失败 → 恢复快照
- **优点**：与现有 Riverpod + HomeState 体系完全一致，无新框架引入
- **缺点**：每个操作需手写快照/回滚，模式固定但重复

### 方案 B：Command Bus（Redux-like）
- 引入 Command/Action 派发机制，操作统一经过 reducer
- **优点**：统一派发，便于日志/追踪/重试
- **缺点**：引入新抽象，当前规模不需要，团队学习成本高

**选择方案 A**，理由：与现有 Riverpod + HomeState 体系一致；乐观更新 + 快照回滚是可重复的模式；方案 B 的价值在规模达到后再演进。

## Intent 层架构

```
lib/
  domain/
    content/
      content_intent.dart      # ContentIntentNotifier（like/save）
    user/
      user_intent.dart         # UserIntentNotifier（follow/unfollow）
  core/
    providers/
      intent_providers.dart    # contentIntentProvider, userIntentProvider
```

### ContentIntentNotifier 骨架

```dart
class ContentIntentNotifier extends Notifier<void> {
  @override
  void build() {}

  Future<void> like(String postId) async {
    final homeState = ref.read(homeStateProvider.notifier);
    final wasLiked = ref.read(homeStateProvider).likedPosts.contains(postId);
    // 乐观更新
    homeState.toggleLike(postId);
    try {
      if (!wasLiked) {
        await ref.read(contentRepositoryProvider).likePost(postId);
      } else {
        await ref.read(contentRepositoryProvider).unlikePost(postId);
      }
    } catch (_) {
      // 回滚
      homeState.toggleLike(postId);
    }
  }

  Future<void> save(String postId) async { /* 同 like 模式 */ }
}
```

### user_profile/service.yaml 新增路由

```yaml
routes:
  - id: FollowUser
    method: POST
    path: /v1/users/{userId}/follow
    auth: required
  - id: UnfollowUser
    method: DELETE
    path: /v1/users/{userId}/follow
    auth: required
```

## 数据流（目标态）

```
ImmersiveImageViewer（点击赞）
    │ ref.read(contentIntentProvider).like(dto.id)
    ▼
ContentIntentNotifier.like(postId)
    ├── 快照 likedPosts
    ├── HomeState.toggleLike(postId)  ─→  UI 立即更新（乐观）
    └── ContentRepository.likePost(postId)  [async]
            ├── 成功 ─→ 无操作（HomeState 已正确）
            └── 失败 ─→ HomeState.toggleLike(postId)  [回滚]

ImmersiveImageViewer（点击关注）
    │ ref.read(userIntentProvider).follow(dto.authorId)
    ▼
UserIntentNotifier.follow(userId)
    ├── HomeState.toggleFollow(userId)  [乐观]
    └── UserRepository.followUser(userId)  [async, 失败回滚]
```

## 适用场景与约束

- **适用**：`content-display-journey-consistency` 所有媒体类型的互动操作
- **不适用**：评论发送；圈子关注（需扩展 `CircleIntent`）
- **约束**：`user_profile/service.yaml` 须在 M1 完成后，`UserRepository` Remote 实现才可写 URL；Mock 实现可先行完成

## 未来演进

- 扩展到圈子关注：复用 `UserIntentNotifier` 模式，新增 `CircleIntent`
- 意图幂等性：在 Intent layer 加 debounce（300ms）防止重复点赞
- 重试策略：网络抖动时 Intent 内部 retry（当前不做，由 `ContentRepository` Remote 实现自行处理）
- 操作日志：Intent 调用时通过 `BehaviorRepository` 上报行为事件（可接入 analytics）
