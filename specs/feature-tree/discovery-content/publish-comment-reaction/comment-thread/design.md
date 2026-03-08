# comment-thread 设计（商用级评论系统）

> **版本**：V1 Design — 2026-03-08
> **上游 spec**：spec.md V1 PRD（F1~F20, A1~A23）已稳定
> **审核流水线**：F15/A21 标记 deferred，待运营系统统一规划；本设计仅保留事件钩子接口

---

## 一、设计动因

当前评论系统 8 个入口中仅 2 个能提交、0 个能加载历史评论；云侧 Handler 全部 `handleNotImplemented`；端侧无类型化 DTO、无状态管理、无分页。需要一次性完成端云闭环，达到商用上线标准。

本设计遵循已有架构模式（MongoDB 持久化 + PostRepository 接口 + 领域事件 + 游标分页 + Riverpod 状态管理），在此基础上引入热评缓存、乐观更新状态机、评论专属 Provider 和手势弹窗。

---

## 二、方案对比

### 2.1 云侧热评排序

| 维度 | 方案 A：纯 DB 排序 | 方案 B：Redis ZSet 缓存 + DB 兜底 |
|------|-------------------|----------------------------------|
| 实现复杂度 | 低（索引 + ORDER BY） | 中（ZSet 维护 + 回源） |
| 读性能（P95） | 冷帖 <100ms，热帖 >500ms | 冷帖走 DB <100ms，热帖走 Redis <50ms |
| 写入延迟 | 无额外开销 | ZSet ZADD 单次 ~1ms |
| 一致性 | 强一致 | 最终一致（TTL 刷新窗口内） |
| 10 万评论帖 | 性能下降，需深翻页优化 | 热评 Top-N 从 ZSet 读，性能稳定 |
| 运维复杂度 | 低 | 需 Redis 容量规划 |
| 演进到超热帖分片 | 困难 | ZSet 天然支持 ZUNIONSTORE |

**选定：方案 B** — 冷帖走 DB（绝大多数场景），热帖走 Redis ZSet 缓存。理由：10 万+评论帖的性能目标（P95 < 800ms）在纯 DB 方案下无法满足；Redis ZSet 方案与业界（TikTok/微博/小红书）架构一致，可演进到超热帖分片。

### 2.2 端侧状态管理

| 维度 | 方案 A：局部 StatefulWidget（现有模式） | 方案 B：CommentProvider (StateNotifier.family) |
|------|----------------------------------------|-----------------------------------------------|
| 状态共享 | 弹窗内局部，关闭即丢 | Provider 持有，跨弹窗共享 |
| 乐观更新 | 需手动管理 | 统一状态机 |
| 分页 | 需手动 cursor 管理 | Provider 内封装 |
| 评论计数同步 | 需手动回传 | Provider 联动 DiscoveryState |
| 测试性 | 需 Widget 测试 | 可单独测 Provider 逻辑 |
| 复杂度 | 低 | 中 |

**选定：方案 B** — CommentProvider 统一管理评论状态。理由：8 个入口需要一致的行为（加载/提交/删除/点赞/排序切换），局部状态无法保证一致性；乐观更新 + 错误回滚需要统一状态机；与 chat 消息 Provider 模式一致。

### 2.3 评论弹窗

| 维度 | 方案 A：固定高度 ModalBottomSheet（现有） | 方案 B：DraggableScrollableSheet |
|------|---------------------------------------|----------------------------------|
| 手势关闭 | 仅关闭按钮 | 下拉手势 + 关闭按钮 |
| 高度自适应 | 固定 50%/70%/100% | 连续拖拽 50%~90% |
| iOS 语义 | 不符合 iOS 交互预期 | 符合 iOS 标准底部面板 |
| 列表联动 | 无 | 列表滚动到顶后可下拉关闭 |

**选定：方案 B** — DraggableScrollableSheet 实现手势弹窗。理由：对标 TikTok/小红书的交互体验；iOS 语义规范要求。

---

## 三、组件图

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              端侧 (Flutter)                                 │
│                                                                             │
│  ┌──────────────────────┐   ┌───────────────────────┐                      │
│  │  8 个入口页面/组件     │──▶│  CommentViewerModal   │                      │
│  │  (discovery/content/  │   │  DraggableScrollable  │                      │
│  │   user/media)         │   │  Sheet                │                      │
│  └──────────────────────┘   └──────────┬────────────┘                      │
│                                        │                                    │
│                               ┌────────▼─────────┐                         │
│                               │  CommentProvider  │                         │
│                               │  (StateNotifier   │                         │
│                               │   .family<postId>)│                         │
│                               └────────┬─────────┘                         │
│                                        │                                    │
│               ┌────────────────────────┼────────────────────┐              │
│               ▼                        ▼                    ▼              │
│  ┌─────────────────┐     ┌──────────────────┐    ┌──────────────────┐     │
│  │ContentRepository│     │ContentInteraction │    │AppConfigProvider │     │
│  │ (listComments,  │     │Repository         │    │ (max_length,     │     │
│  │  createComment, │     │ (likeComment,     │    │  reply_preview,  │     │
│  │  deleteComment) │     │  unlikeComment)   │    │  fold_lines)     │     │
│  └────────┬────────┘     └────────┬──────────┘    └────────┬─────────┘     │
│           │                       │                        │               │
│           └───────────────────────┼────────────────────────┘               │
│                                   │ HTTP                                    │
└───────────────────────────────────┼─────────────────────────────────────────┘
                                    │
┌───────────────────────────────────┼─────────────────────────────────────────┐
│                              云侧 (Go)                                      │
│                                   │                                         │
│           ┌───────────────────────▼──────────────────────┐                  │
│           │              ContentHandler                   │                  │
│           │  ListComments / CreateComment / DeleteComment  │                  │
│           │  LikeComment / UnlikeComment                  │                  │
│           │  ListCommentsByAuthor / ListCommentsForPostAuthor │              │
│           └───────────────────────┬──────────────────────┘                  │
│                                   │                                         │
│           ┌───────────────────────▼──────────────────────┐                  │
│           │            CommentService (domain)            │                  │
│           │  CreateComment / DeleteComment / ListComments  │                  │
│           │  Counter 更新 / 权限校验 / 事件发布              │                  │
│           └──────┬──────────────┬──────────────┬─────────┘                  │
│                  │              │              │                             │
│        ┌─────────▼────┐  ┌─────▼──────┐  ┌───▼──────────┐                  │
│        │ CommentStore │  │ Redis      │  │ EventPublisher│                  │
│        │ (MongoDB)    │  │ (ZSet 热评  │  │ CommentCreated│                  │
│        │ comments 集合 │  │  点赞计数   │  │ CommentDeleted│                  │
│        │              │  │  频率限制)  │  │ CommentLiked  │                  │
│        └──────────────┘  └────────────┘  └──────────────┘                  │
│                                                                             │
│        ┌──────────────────────────────────────────────────┐                  │
│        │  config.yaml (sys.content.comment.*)             │                  │
│        │  max_length / rate_limit / hot_post / cache_ttl  │                  │
│        └──────────────────────────────────────────────────┘                  │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 四、用例图

```
┌──────────────────────────────────────────────────────────────┐
│                         用例图                                │
│                                                              │
│  ┌──────┐                                                    │
│  │ 浏览者 │──── 浏览评论列表（热评/最新排序切换）                  │
│  └──┬───┘     └── 展开回复 / 折叠回复                          │
│     │         └── 长评论展开全文                               │
│     │         └── 翻页加载更多                                 │
│     │                                                        │
│  ┌──▼───┐                                                    │
│  │ 评论者 │──── 发表评论（选择 Persona 身份）                    │
│  └──┬───┘     └── 回复评论（@被回复人）                         │
│     │         └── 点赞评论 / 取消点赞                          │
│     │         └── 删除自己的评论                               │
│     │                                                        │
│  ┌──▼───┐                                                    │
│  │ 帖主  │──── 删除帖下任意评论                                 │
│  └──────┘     └── 查看"收到的评论"                             │
│                                                              │
│  ━━━━━━━━ 异常分支 ━━━━━━━━                                   │
│                                                              │
│  [弱网]   提交超时 → 本地队列 → "发送中"标记                     │
│           → 恢复后自动重试（≤3次）→ 仍失败 → "发送失败"          │
│                                                              │
│  [频率限制] 单用户 >5条/分 → 返回 comment_rate_limited          │
│            → 端侧 Toast 提示"操作过于频繁"                     │
│                                                              │
│  [字数超限] >500字 → 端侧输入框拦截 + 云侧 comment_too_long     │
│                                                              │
│  [列表加载失败] → "加载失败，点击重试" + 保留已加载数据           │
│                                                              │
└──────────────────────────────────────────────────────────────┘
```

---

## 五、主链路流程图

### 5.1 评论创建主链路

```
用户点击发送
    │
    ▼
端侧 CommentProvider
    │
    ├─① 前置校验
    │   ├─ content 非空?
    │   ├─ content ≤ max_length?（从 AppConfigProvider 读取，fallback 500）
    │   └─ 校验失败 → Toast 提示，终止
    │
    ├─② 乐观插入
    │   ├─ 生成 clientCommentId (UUID)
    │   ├─ 构建 optimistic CommentDto (status=sending)
    │   ├─ 插入列表头部 / 回复区
    │   ├─ 帖外 commentCount + 1（联动 DiscoveryState）
    │   └─ UI 即时渲染
    │
    ├─③ 异步提交
    │   ├─ contentRepository.createComment(postId, content, replyToCommentId, personaId)
    │   ├─ 成功 → 替换 optimistic 为 confirmed（id, createdAt 来自服务端）
    │   │       status = visible
    │   └─ 失败 ─┬─ 网络超时 → 进入本地重试队列 → status = sending
    │            └─ 业务错误 → 回滚：移除 optimistic + commentCount - 1
    │                         → Toast 错误信息
    │
    ▼
云侧 ContentHandler.handleCreateComment
    │
    ├─① 频率限制 → RateLimiter.Allow()? → 否 → 429 comment_rate_limited
    ├─② 字数校验 → len(content) ≤ config.max_length? → 否 → 400 comment_too_long
    ├─③ CommentService.CreateComment
    │   ├─ 生成 Snowflake/NanoID
    │   ├─ 写入 CommentStore (MongoDB comments 集合)
    │   ├─ Post.commentCount++ + Post.UpdatedAt
    │   ├─ 若 replyToCommentId != "" → 父评论 replyCount++
    │   ├─ 若 Post.commentCount ≥ hot_post.threshold → 更新 Redis ZSet（ZADD 热评分值）
    │   └─ 发布 CommentCreated 事件
    │       ├─ [审核钩子] 未来审核流水线消费（deferred）
    │       └─ [通知钩子] notification 域消费 → 推送通知
    │
    └─④ 返回 201 { id, postId, authorId, ... , createdAt }
```

### 5.2 评论列表加载流程

```
用户打开评论弹窗
    │
    ▼
CommentProvider.loadComments(postId, sortBy: hot|latest)
    │
    ├─ state = loading
    │
    ├─ contentRepository.listComments(postId, sort, cursor, limit=20)
    │
    ▼
云侧 ContentHandler.handleListComments
    │
    ├─ sort=hot?
    │   ├─ 是 → Post.commentCount ≥ threshold?
    │   │       ├─ 是 → Redis ZREVRANGE comment_hot:{postId} 0 limit → 返回缓存
    │   │       └─ 否 → MongoDB idx_comments_hot 查询
    │   └─ 否 → MongoDB idx_comments_post_created 查询（cursor 分页）
    │
    ├─ 构建 CommentPage { items: [...], nextCursor: "..." }
    │   ├─ 每条 Comment 附带 isAuthor (authorId == post.authorId)
    │   └─ nextCursor = 最后一条的 _id（不透明字符串）
    │
    └─ 返回 200 CommentPage
    │
    ▼
CommentProvider
    ├─ 解析 CommentPage → List<CommentDto>
    ├─ 按 rootCommentId 分组（一级 + 回复）
    ├─ state = loaded (comments, nextCursor, sortBy)
    └─ UI 渲染 2 级嵌套列表

滚动到底 → CommentProvider.loadMore(postId)
    ├─ nextCursor 非空? → 否 → 终止
    ├─ state.isLoadingMore = true
    ├─ contentRepository.listComments(postId, sort, nextCursor, limit=20)
    ├─ 追加到现有列表
    └─ state.isLoadingMore = false
```

### 5.3 评论点赞流程

```
用户点击 ❤
    │
    ▼
CommentProvider.toggleLike(commentId)
    │
    ├─ 乐观更新：likeCount ± 1 + isLiked 切换
    │
    ├─ isLiked?
    │   ├─ 是 → contentInteractionRepository.likeComment(commentId)
    │   └─ 否 → contentInteractionRepository.unlikeComment(commentId)
    │
    ▼
云侧 ContentHandler.handleLikeComment / handleUnlikeComment
    │
    ├─ Redis SISMEMBER comment_like:{commentId} userId → 已赞?
    │   ├─ 重复赞 → 409 comment_like_duplicate
    │   └─ 新赞 → SADD + INCR counter:comment:{commentId}:like
    │
    ├─ 异步刷盘（每 5s 或 100 次批量写 MongoDB）
    │
    ├─ 若所属 Post 是热帖 → ZADD 更新 ZSet 中该评论的热评分值
    │
    └─ 发布 CommentLiked 事件
```

---

## 六、关键设计决策

### 6.1 热评排序算法

热评分值 = `likeCount × 10 + replyCount × 5 + recency_bonus`

其中 recency_bonus：
```
age_hours = (now - createdAt).hours
if age_hours < 1:     bonus = 100
elif age_hours < 6:   bonus = 50
elif age_hours < 24:  bonus = 20
elif age_hours < 72:  bonus = 10
else:                 bonus = 0
```

ZSet score 在以下时机更新：
- 评论创建（初始分值）
- 评论被赞/取消赞（likeCount 变化）
- 评论被回复（replyCount 变化）
- ZSet TTL 到期后回源 DB 重建

### 6.2 游标分页实现

遵循现有 MongoDB cursor 模式（`mongo_post_store.go`）：

```go
// 最新排序：按 createdAt DESC
if cursor != "" {
    var cursorDoc Comment
    if err := coll.FindOne(ctx, bson.M{"_id": cursor}).Decode(&cursorDoc); err == nil {
        filter["createdAt"] = bson.M{"$lt": cursorDoc.CreatedAt}
    }
}
opts := options.Find().SetSort(bson.D{{Key: "createdAt", Value: -1}}).SetLimit(int64(limit))

// 热评排序：按 score DESC
if cursor != "" {
    var cursorDoc Comment
    if err := coll.FindOne(ctx, bson.M{"_id": cursor}).Decode(&cursorDoc); err == nil {
        cursorScore := computeHotScore(cursorDoc)
        filter["$or"] = bson.A{
            bson.M{"hotScore": bson.M{"$lt": cursorScore}},
            bson.M{"hotScore": cursorScore, "_id": bson.M{"$lt": cursor}},
        }
    }
}
opts := options.Find().SetSort(bson.D{{Key: "hotScore", Value: -1}, {Key: "_id", Value: -1}}).SetLimit(int64(limit))
```

nextCursor = 最后一条记录的 `_id`；为空表示无更多数据。

### 6.3 CommentProvider 状态机

```dart
class CommentState {
  final List<CommentDto> comments;       // 一级评论
  final Map<String, List<CommentDto>> replies;  // rootCommentId → 回复列表
  final Map<String, bool> expandedReplies;      // 是否展开回复
  final Set<String> likedCommentIds;            // 已赞评论
  final String? nextCursor;
  final CommentSortBy sortBy;                   // hot | latest
  final CommentLoadStatus status;               // initial | loading | loaded | loadingMore | error
  final String? error;
  final List<PendingComment> pendingQueue;      // 待发送队列（弱网）
}

enum CommentSortBy { hot, latest }
enum CommentLoadStatus { initial, loading, loaded, loadingMore, error }

class PendingComment {
  final String clientId;
  final String content;
  final String? replyToCommentId;
  final String? personaId;
  final int retryCount;
  final PendingStatus status;  // sending | retrying | failed
}
```

Provider 声明（与 ChatMessageProvider 模式一致）：

```dart
final commentProvider = StateNotifierProvider.family<
    CommentNotifier, CommentState, String>(
  (ref, postId) {
    final repo = ref.watch(contentRepositoryProvider);
    final interactionRepo = ref.watch(contentInteractionRepositoryProvider);
    final appConfig = ref.watch(appConfigProvider);
    return CommentNotifier(repo, interactionRepo, appConfig, postId);
  },
);
```

### 6.4 乐观更新状态机

```
              ┌──────────┐
              │  idle     │
              └────┬─────┘
                   │ user submits
              ┌────▼─────┐
              │ optimistic│ ← 本地插入 + 计数+1 + UI 即时渲染
              │ (sending) │
              └────┬─────┘
                   │
          ┌────────┼────────┐
          │ success         │ error
     ┌────▼─────┐     ┌────▼─────┐
     │ confirmed│     │ 网络错误? │
     │ (visible)│     └────┬─────┘
     └──────────┘     ┌────┼────────┐
                      │ yes         │ no (business error)
                 ┌────▼─────┐  ┌───▼──────┐
                 │ enqueue  │  │ rollback  │ ← 移除 optimistic + 计数-1
                 │ (retry)  │  │ + toast   │
                 └────┬─────┘  └──────────┘
                      │ network restored
                      │ retry ≤ 3
                 ┌────▼─────┐
                 │ re-submit│
                 └────┬─────┘
                 ┌────┼────────┐
                 │ success     │ all retries exhausted
            ┌────▼─────┐  ┌───▼──────┐
            │ confirmed│  │ rollback  │
            └──────────┘  │ + toast   │
                          └──────────┘
```

### 6.5 评论弹窗（DraggableScrollableSheet）

```dart
showModalBottomSheet(
  context: context,
  isScrollControlled: true,
  backgroundColor: Colors.transparent,
  builder: (_) => DraggableScrollableSheet(
    initialChildSize: 0.7,
    minChildSize: 0.5,
    maxChildSize: 0.9,
    builder: (context, scrollController) => Container(
      decoration: BoxDecoration(
        color: AppColors.surface,
        borderRadius: BorderRadius.vertical(
          top: Radius.circular(AppSpacing.lg),
        ),
      ),
      child: Column(
        children: [
          _DragHandle(),             // 拖拽条
          _TitleBar(postId),         // "评论 (N)" + 排序切换
          Expanded(
            child: _CommentList(     // 2 级嵌套列表
              scrollController: scrollController,
              postId: postId,
            ),
          ),
          _CommentInputBar(postId),  // 输入栏
        ],
      ),
    ),
  ),
);
```

列表滚动到顶后继续下拉 → Sheet 收缩 → 低于 minChildSize → 自动关闭。

### 6.6 2 级评论嵌套渲染

```dart
ListView.builder(
  controller: scrollController,
  itemCount: comments.length + (hasMore ? 1 : 0),
  itemBuilder: (context, index) {
    if (index == comments.length) return _LoadMoreIndicator();
    
    final comment = comments[index];
    final commentReplies = replies[comment.id] ?? [];
    final isExpanded = expandedReplies[comment.id] ?? false;
    final previewCount = appConfig.replyPreviewCount;
    
    return Column(
      children: [
        _CommentTile(comment: comment, isAuthor: comment.isAuthor),
        
        // 回复区（缩进）
        Padding(
          padding: EdgeInsets.only(left: AppSpacing.xl * 2),  // 48px
          child: Column(
            children: [
              ...commentReplies.take(isExpanded ? commentReplies.length : previewCount)
                  .map((reply) => _ReplyTile(reply: reply)),
              
              if (!isExpanded && comment.replyCount > previewCount)
                _ExpandRepliesButton(
                  count: comment.replyCount - previewCount,
                  onTap: () => provider.expandReplies(comment.id),
                ),
            ],
          ),
        ),
      ],
    );
  },
);
```

### 6.7 App Config Endpoint

新增通用 API 端点（不仅评论用，全局可复用）：

```
GET /v1/config/app
Response 200:
{
  "content": {
    "comment": {
      "max_length": 500,
      "reply_preview_count": 2,
      "fold_line_count": 3
    }
  },
  "chat": {
    "max_message_length": 5000
  },
  "media": {
    "chat_video_max_duration_ms": 300000
  }
}
```

云侧实现：ConfigHandler 从 `RuntimeConfigProvider` 或 config.yaml 读取 `sys.*` 前缀的配置，组装为 JSON 返回。

端侧实现：

```dart
final appConfigProvider = StateProvider<AppConfig>((ref) {
  return AppConfig.defaults(); // codegen fallback
});

class AppConfigNotifier extends StateNotifier<AppConfig> {
  AppConfigNotifier(this._repo) : super(AppConfig.defaults());
  final ConfigRepository _repo;

  Future<void> load() async {
    try {
      final config = await _repo.getAppConfig();
      state = config;
    } catch (_) {
      // fallback to defaults, log warning
    }
  }
}
```

启动时调用一次 `load()`；V2 可通过 WebSocket 热更新。

### 6.8 CommentDto 设计

```dart
class CommentDto {
  final String id;
  final String postId;
  final String authorId;
  final String? personaId;
  final String displayName;
  final String avatarUrl;
  final String content;
  final String? replyToCommentId;
  final String? replyToUserId;
  final String? replyToDisplayName;
  final int replyCount;
  final int likeCount;
  final String status;      // visible | hidden | deleted
  final bool isAuthor;      // 是否帖主
  final DateTime createdAt;

  factory CommentDto.fromMap(Map<String, dynamic> map) => ...;
  CommentDto copyWith({...}) => ...;
}
```

### 6.9 ContentRepository 评论方法扩展

Abstract 新增：

```dart
abstract class ContentRepository {
  // ... 现有方法 ...

  // 评论
  Future<CommentPage> listComments({
    required String postId,
    String? cursor,
    int limit = 20,
    String sort = 'hot',  // hot | latest
  });
  Future<CommentDto> createComment({
    required String postId,
    required String content,
    String? replyToCommentId,
    String? personaId,
  });
  Future<void> deleteComment({required String postId, required String commentId});

  // 评论点赞
  Future<void> likeComment({required String commentId});
  Future<void> unlikeComment({required String commentId});

  // 个人主页评论
  Future<CommentPage> listCommentsByAuthor({String? cursor, int limit = 20});
  Future<CommentPage> listCommentsForPostAuthor({String? cursor, int limit = 20});
}

class CommentPage {
  final List<CommentDto> items;
  final String? nextCursor;
}
```

返回类型从 `Map<String, dynamic>` 升级为 `CommentDto` / `CommentPage`。

### 6.10 云侧 CommentStore 接口

```go
type CommentStore interface {
    Create(ctx context.Context, comment *Comment) error
    FindByID(ctx context.Context, id string) (*Comment, bool)
    SoftDelete(ctx context.Context, id string) error
    ListByPost(ctx context.Context, postID, cursor string, limit int, sort string) ([]Comment, string, error)
    ListByAuthor(ctx context.Context, authorID, cursor string, limit int) ([]Comment, string, error)
    ListForPostAuthor(ctx context.Context, postAuthorID, cursor string, limit int) ([]Comment, string, error)
    IncrementReplyCount(ctx context.Context, parentCommentID string, delta int) error
}
```

遵循 PostRepository 模式：接口在 domain/infrastructure 层，MongoDB 实现在 `infrastructure/persistence/mongo_comment_store.go`。

### 6.11 Redis 缓存策略

| 缓存 Key | Type | TTL | 写入时机 | 读取时机 |
|----------|------|-----|---------|---------|
| `comment_hot:{postId}` | ZSet | 300s | 评论创建/点赞/回复 | ListComments sort=hot 且 commentCount≥threshold |
| `comment_like:{commentId}` | Set | null | LikeComment/UnlikeComment | 去重检查 |
| `counter:comment:{commentId}:like` | String | null | LikeComment (INCR) | 读取赞数 |
| `comment_summary:{postId}` | Hash | 3600s | 已有定义 | 评论摘要 |

热帖判定：`Post.commentCount ≥ config.hot_post.threshold`（默认 100）。

ZSet score = `hotScore`（§6.1 公式计算结果）。

### 6.12 频率限制实现

```go
// 每 postId + userId 一个 RateLimiter
type CommentRateLimiter struct {
    userLimiters sync.Map  // userId → *governance.RateLimiter
    postLimiters sync.Map  // postId → *governance.RateLimiter
    userRPM      int       // from config
    postRPM      int       // from config
}

func (rl *CommentRateLimiter) AllowCreate(userID, postID string) error {
    userLimiter := rl.getOrCreate(&rl.userLimiters, userID, rl.userRPM/60)
    if !userLimiter.Allow() {
        return generated.AppErrorFromCommentRateLimited("user rate exceeded")
    }
    postLimiter := rl.getOrCreate(&rl.postLimiters, postID, rl.postRPM/60)
    if !postLimiter.Allow() {
        return generated.AppErrorFromCommentRateLimited("post rate exceeded")
    }
    return nil
}
```

### 6.13 个人主页评论

| 端点 | 路由 | 查询 | 索引 |
|------|------|------|------|
| ListCommentsByAuthor | `GET /v1/content/users/me/comments` | authorId=currentUser, cursor, limit | idx_comments_author |
| ListCommentsForPostAuthor | `GET /v1/content/users/me/received-comments` | 先查 currentUser 的 posts → 再查这些 postIds 下的评论 | idx_comments_post_created |

返回的每条评论附带 `postSummary`（帖子标题/封面/类型），方便端侧跳转。

### 6.14 评论通知骨架

```
CommentCreated 事件
    │
    ├─ notification-consumer 消费
    │   ├─ 帖主 ≠ 评论者? → 生成 "有人评论了你的帖子" 通知
    │   └─ replyToUserId 存在且 ≠ 评论者? → 生成 "有人回复了你的评论" 通知
    │
    └─ notification 域负责：存储通知 + 推送渠道（APNs/FCM）
```

V1 只发布事件 + 消费骨架代码；推送渠道由 notification 域承接。

### 6.15 Persona 身份切换

```
评论输入栏
    │
    ├─ 头像点击 → Persona 选择器弹窗
    │   ├─ 列出用户所有 persona（主身份 + persona 列表）
    │   └─ 选择后 → CommentProvider.setActivePersona(personaId)
    │
    ├─ 发送评论时
    │   ├─ personaId = activePersona ?? null (null = 主身份)
    │   └─ createComment(postId, content, replyToCommentId, personaId)
    │
    └─ 评论展示
        ├─ personaId != null → 显示 persona 头像/昵称
        └─ personaId == null → 显示主身份头像/昵称
```

### 6.16 入口打通方案

所有入口统一调用 `CommentViewer.showModal(context, postId)`，内部通过 `ref.read(commentProvider(postId))` 获取状态。

| 入口 | 当前代码 | 改造 |
|------|---------|------|
| E1 微趣 Feed | `moment_social_feed.dart` | 已有 onSubmitComment，补充首屏 listComments |
| E2 作品沉浸 | `works_immersive_viewer.dart` | 同 E1 |
| E3 微趣评论数 | `discovery_page.dart` | 补充 onSubmitComment |
| E4 图片沉浸 | `immersive_image_viewer.dart` | 接通完整评论流 |
| E5 视频沉浸 | `immersive_video_viewer.dart` | 同 E4 |
| E6 MediaPostCard | `media_post_card.dart` | 同 E4 |
| E7 文章详情 | `article_detail_page.dart` | 替换 no-op |
| E8 个人主页 | `author_profile_page.dart` | 新增 Tab |

**统一参数**：`CommentViewer.showModal(context: context, postId: postId)` — 所有其他参数从 Provider 内部获取，入口代码极简。

---

## 七、编码规范与设计 Token

### 7.1 Dart 视觉 Token

| 元素 | Token | 禁止 |
|------|-------|------|
| 评论头像 | `AppSpacing.xxxl` (36px) | 硬编码 `36` |
| 回复头像 | `AppSpacing.xl` (24px) | 硬编码 `24` |
| 用户名 | `AppTypography.bodyBold` | 硬编码 fontSize |
| 评论正文 | `AppTypography.body` | 硬编码 fontSize |
| 时间/附属 | `AppTypography.caption` | 硬编码 fontSize |
| 作者标签 | `AppTypography.captionBold` + `AppColors.primary` | — |
| 文本主色 | `AppColors.textPrimary` | 硬编码 Color |
| 附属色 | `AppColors.textSecondary` | 硬编码 Color |
| 点赞色 | `AppColors.danger` | 硬编码 Color |
| 弹窗背景 | `AppColors.surface` | 硬编码 Color |
| 分隔线 | `AppColors.divider` | 硬编码 Color |
| 评论间距 | `AppSpacing.md` | 硬编码 EdgeInsets |
| 回复缩进 | `AppSpacing.xl * 2` (48px) | 硬编码 padding |
| 弹窗圆角 | `AppSpacing.lg` | 硬编码 radius |
| 输入栏高度 | `AppSpacing.xxxl + AppSpacing.md` | 硬编码 height |

### 7.2 Go 代码约束

| 约束 | 说明 |
|------|------|
| CommentStore 仅在 `infrastructure/persistence/` | domain 禁止 import 数据库驱动 |
| 配置读取 | `RuntimeConfigProvider` 或 config struct，禁止 `os.Getenv` |
| 错误返回 | `generated.AppErrorFromXxx()`，禁止自定义 error struct |
| 事件发布 | `repository.DomainEvent`，禁止自定义 MQ 序列化 |
| 缓存 TTL | 从 `EntityRegistry.GetCacheTTL()` 或 config 读取，禁止硬编码 |

---

## 八、适用场景与约束

### 8.1 适用场景

- 单帖评论量 0 ~ 10 万+
- 5 种内容类型（微趣/图片/视频/文章/圈子帖）
- 弱网（高延迟 >3s、断网、恢复）
- 多 Persona 身份切换
- 热帖（评论数 ≥ 100）的高读 QPS 场景

### 8.2 不适用

- 超热帖分片（单帖 >10 万 + 读 QPS >1 万）→ 需 ZSet 逻辑分片 + ZUNIONSTORE
- 评论实时推送（WebSocket）→ 依赖 realtime 域
- 评论全文搜索 → 依赖 ES
- 审核流水线 → deferred，待运营系统统一规划

---

## 九、未来演进

| 方向 | 当前态 | 目标态 | 差距 | 触发条件 |
|------|--------|--------|------|---------|
| 超热帖分片 | 单 ZSet | 逻辑分片 A/B/C + ZUNIONSTORE | 需分片路由 | 单帖 >10 万 + QPS >1 万 |
| 二级分页 | 回复扁平 | 先主评论游标再按 root 拉回复 | 独立游标 | 单帖回复 >1 万 |
| 实时推送 | 轮询/手动刷新 | WebSocket 推送新评论 | realtime 基础设施 | realtime 域就绪 |
| 富媒体 | 纯文本 | 表情 → 图片 | 审核增强 | V2/V3 迭代 |
| App Config 热更新 | 启动拉取 | WebSocket 推送 | 复用 realtime 通道 | realtime 域就绪 |
| 审核流水线 | 事件钩子 | 完整审核流水线 | 运营系统 | 运营系统规划完成 |

---

## 十、国际化（i18n）约束

| 类型 | 规则 | 来源 |
|---|---|---|
| 静态文案 | `UITextConstants.*` | `02-dart-coding §2.3` |
| 模板文案（含参数） | `context.l10n.*Template()` | ARB 定义 |
| 相对时间 | `context.l10n.justNow` / `minutesAgoTemplate` / `hoursAgoTemplate` / `daysAgoTemplate` / `monthDayTemplate` | 已有 l10n 基础设施 |
| 禁止 | 任何 `.dart` 文件中硬编码中文/英文用户可见字面量 | `02-dart-coding §2.3` |

评论系统涉及的文案：排序标签（最新/最热）、作者标签、回复前缀、展开回复模板、Tab 标题、空态/错误提示、相对时间，均须通过上述渠道注入。

---

## 十一、上游 Spec 评审

spec.md V1 PRD 与 acceptance.yaml A1~A23 足以支撑本设计，以下调整：
- **A21（先发后审）**：标记为 deferred，仅保留事件钩子接口
- **A22（评论通知）**：V1 实现事件发布 + 消费骨架，推送渠道由 notification 域承接
- 无其他阻断项
