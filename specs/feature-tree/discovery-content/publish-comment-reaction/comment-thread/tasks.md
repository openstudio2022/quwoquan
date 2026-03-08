# 开发任务：comment-thread（商用级评论系统）

> **交付顺序**：metadata/契约修复 → codegen → 云侧实现 → 端侧 DTO & Repository → UI 重构 → 入口打通 → 个人主页 → 配置统一 → 测试 → 门禁
> **设计参考**：design.md V1 Design（方案 B 选定：Redis ZSet 热评缓存 + CommentProvider 状态管理 + DraggableScrollableSheet 手势弹窗）

---

## 当前交付任务

### Phase 0：Metadata 修复与扩展（M1~M6）

- [ ] **M1**：修复 OpenAPI Delete 路径 → 统一为 `DELETE /v1/content/posts/{postId}/comments/{commentId}`，与 service.yaml 对齐
- [ ] **M2**：fields.yaml 新增 `Comment.replyCount` (int)、`Comment.hotScore` (float, 计算字段)
- [ ] **M3**：service.yaml 新增端点：
  - `LikeComment`：`POST /v1/content/comments/{commentId}/like`
  - `UnlikeComment`：`DELETE /v1/content/comments/{commentId}/like`
  - `ListCommentsByAuthor`：`GET /v1/content/users/me/comments`
  - `ListCommentsForPostAuthor`：`GET /v1/content/users/me/received-comments`
  - `GetAppConfig`：`GET /v1/config/app`（通用端点，非评论专属）
- [ ] **M4**：events.yaml 新增事件：`CommentLiked`
- [ ] **M5**：storage.yaml 新增：
  - `idx_comments_hot` 索引 `(postId, hotScore DESC, _id DESC)`
  - Redis 缓存 key：`comment_hot:{postId}` (ZSet, TTL 300s), `comment_like:{commentId}` (Set, null), `counter:comment:{commentId}:like` (String, null)
- [ ] **M6**：errors.yaml 新增错误码：`comment_too_long`、`comment_rate_limited`、`comment_like_duplicate`（含 l10n_key + user_message.zh/en）
- [ ] `make verify-metadata` 通过

### Phase 1：Codegen（C1~C2）

- [ ] **C1**：`make codegen` — 云侧 codegen 产出（错误码常量、路由骨架）
- [ ] **C2**：`make codegen-app` — 端侧 codegen 产出 CommentDto 类型化 DTO + 错误码枚举 + metadata 常量

### Phase 2：云侧实现（S1~S8）

- [ ] **S1**：`mongo_comment_store.go` — CommentStore 接口 + MongoDB 实现
  - `Create`：写入 comments 集合
  - `FindByID`：按 _id 查询
  - `SoftDelete`：标记 status=deleted + deletedAt
  - `ListByPost`：cursor 分页，支持 hot（hotScore DESC）/ latest（createdAt DESC）两种排序
  - `ListByAuthor`：按 authorId 查询 + cursor 分页（idx_comments_author）
  - `ListForPostAuthor`：先查 posts by authorId → 再查 comments by postIds（idx_comments_post_created）
  - `IncrementReplyCount`：原子更新 replyCount
- [ ] **S2**：`comment_service.go` — 领域服务
  - `CreateComment`：生成 ID → 写入 Store → Post.commentCount++ → 若 replyTo 则父评论 replyCount++ → 计算 hotScore → 若 Post.commentCount ≥ threshold 则 ZADD Redis ZSet → 发布 CommentCreated → 返回 Comment
  - `DeleteComment`：权限校验（作者或帖主）→ SoftDelete → Post.commentCount-- → 若 replyTo 则父评论 replyCount-- → 若热帖则 ZREM → 发布 CommentDeleted
  - `ListComments`：热帖+hot排序 → Redis ZREVRANGE 优先 → 回源 DB；其他 → DB cursor 分页
  - 热评分值公式：`likeCount×10 + replyCount×5 + recency_bonus`（见 design.md §6.1）
- [ ] **S3**：评论点赞 — 在 CommentService 或独立 CommentLikeService
  - `LikeComment`：Redis SISMEMBER 去重 → SADD → INCR counter → 更新 ZSet score → 异步刷盘 → 发布 CommentLiked
  - `UnlikeComment`：SREM → DECR → 更新 ZSet → 异步刷盘
  - 刷盘间隔从 `config.comment.like_flush_interval_ms` 读取（默认 5000ms）
- [ ] **S4**：审核钩子（仅事件接口，不实现审核流水线）
  - CommentCreated 事件已包含评论全量字段
  - 预留 CommentModerated 事件定义
  - 审核流水线消费端 → deferred（待运营系统统一规划）
- [ ] **S5**：HTTP Handler 实现
  - `handleListComments`：解析 postId + cursor + limit + sort → 调用 CommentService.ListComments → 返回 CommentPage
  - `handleCreateComment`：频率限制 → 字数校验 → 调用 CommentService.CreateComment → 返回 201
  - `handleDeleteComment`：解析 postId + commentId → 调用 CommentService.DeleteComment → 返回 204
  - `handleLikeComment` / `handleUnlikeComment`：解析 commentId → 调用点赞服务 → 返回 200/204
  - `handleListCommentsByAuthor` / `handleListCommentsForPostAuthor`：cursor 分页 → 返回 CommentPage（附带 postSummary）
  - `handleGetAppConfig`：从 config 读取 `sys.*` 参数 → 组装 JSON → 返回 200
- [ ] **S6**：字数校验 — Handler 层 `len(content) > config.GetInt("sys.content.comment.max_length")` → 返回 `comment_too_long`
- [ ] **S7**：频率限制 — CommentRateLimiter（per-user + per-post），参数从 config 读取，超限返回 `comment_rate_limited`
- [ ] **S8**：热帖缓存
  - 评论数 ≥ threshold → ZADD comment_hot:{postId} score=hotScore member=commentId
  - ListComments sort=hot → ZREVRANGE 优先，cache miss → DB 回源 + 重建 ZSet
  - ZSet TTL = config.hot_post.cache_ttl_seconds (默认 300s)
  - Top-N = config.hot_post.cache_top_n (默认 50)

### Phase 3：端侧 DTO & Repository（D1~D5）

- [ ] **D1**：CommentDto — 类型化 DTO（若 codegen 产出则使用，否则手写），字段见 design.md §6.8
- [ ] **D2**：CommentPage — `{ items: List<CommentDto>, nextCursor: String? }`
- [ ] **D3**：ContentRepository 升级
  - Abstract 新增：`listComments` / `createComment` / `deleteComment`（返回类型升级为 CommentDto/CommentPage）
  - 新增：`likeComment` / `unlikeComment` / `listCommentsByAuthor` / `listCommentsForPostAuthor`
  - Mock 实现：本地数据 + 模拟延迟 + 模拟分页
  - Remote 实现：CloudRuntimeConfig + CloudRequestHeaders，路径与 service.yaml 一致
- [ ] **D4**：CommentProvider (StateNotifier.family)
  - `CommentState`：comments, replies, expandedReplies, likedCommentIds, nextCursor, sortBy, status, pendingQueue（见 design.md §6.3）
  - `CommentNotifier`：loadComments / loadMore / submitComment / deleteComment / toggleLike / expandReplies / switchSort / setActivePersona / retryPending
  - 乐观更新状态机：optimistic(sending) → confirmed(visible) / enqueue(retry) / rollback(fail)（见 design.md §6.4）
  - 联动 DiscoveryState.commentCount 更新
- [ ] **D5**：AppConfigProvider
  - ConfigRepository：`GET /v1/config/app` → `AppConfig`
  - `AppConfig`：commentMaxLength, replyPreviewCount, foldLineCount（+ codegen fallback 默认值）
  - Provider 注册到 `app_providers.dart`
  - 启动时 load() 一次

### Phase 4：UI 重构（U1~U8）

- [ ] **U1**：CommentViewerModal 重写
  - `DraggableScrollableSheet`（initialChildSize=0.7, min=0.5, max=0.9）
  - 拖拽条 `_DragHandle`（圆角条居中）
  - 弹窗背景 `AppColors.surface` + 圆角 `AppSpacing.lg`
  - 入口统一为 `CommentViewer.showModal(context, postId)`
- [ ] **U2**：_TitleBar — "评论 (N)" + "最热|最新" 排序切换 Tab
- [ ] **U3**：_CommentList — 2 级嵌套渲染
  - 一级评论：`_CommentTile`（头像 36px + 用户名 bodyBold + 时间 caption + 内容 body + 作者标签 + ❤赞数 + 💬回复）
  - 回复区：左缩进 48px + `_ReplyTile`（头像 24px + "回复人 回复 @xxx" + 内容 + 赞数）
  - 回复折叠：默认显示 replyPreviewCount 条 → "展开 N 条回复"按钮
  - 滚动加载：滚到底 → `CommentProvider.loadMore()` → LoadMore indicator
- [ ] **U4**：长评论折叠 — 超过 foldLineCount 行折叠 + "展开全文"按钮（LayoutBuilder 测量行数）
- [ ] **U5**：_CommentInputBar — 输入框 + Persona 头像选择 + 回复指示器 + 字数限制（从 AppConfig 读取）+ 发送按钮
- [ ] **U6**：Persona 选择器 — 头像点击弹出 persona 列表，选择后切换 activePersona
- [ ] **U7**：空态 — "暂无评论，来抢沙发吧" + 引导动画 + 点击聚焦输入框
- [x] **U8**：相对时间 — 复用 `l10n.justNow` / `hoursAgoTemplate` / `minutesAgoTemplate` / `daysAgoTemplate` / `monthDayTemplate`；排序/作者/展开/回复等中文文案已统一收口至 `UITextConstants` 和 `l10n`
- [ ] `python3 scripts/verify_dart_semantic.py` 无新增硬编码视觉字面量

### Phase 5：入口打通（E1~E8）

所有入口统一改为 `CommentViewer.showModal(context: context, postId: postId)`，参数极简化。

- [ ] **E1**：`moment_social_feed.dart` — ActionRow 评论按钮 → `CommentViewer.showModal(context, postId)`
- [ ] **E2**：`works_immersive_viewer.dart` — EngagementBar → 同上
- [ ] **E3**：`discovery_page.dart` — 微趣评论数文字点击 → 同上
- [ ] **E4**：`immersive_image_viewer.dart` — Toolbar 评论 → 同上
- [ ] **E5**：`immersive_video_viewer.dart` — Toolbar 评论 → 同上
- [ ] **E6**：`media_post_card.dart` — 评论按钮 → 同上
- [ ] **E7**：`article_detail_page.dart` — BottomBar 评论 → 同上（替换 no-op）
- [ ] **E8**：`author_profile_page.dart` — 新增"我的评论"/"收到的评论"Tab → 独立列表页

### Phase 6：个人主页评论（P1~P2）

- [ ] **P1**："我发出的评论"Tab — `listCommentsByAuthor` → 列表（评论内容 + 原帖摘要卡片）→ 点击跳转原帖
- [ ] **P2**："我收到的评论"Tab — `listCommentsForPostAuthor` → 列表（评论内容 + 原帖摘要）→ 快捷回复入口

### Phase 7：通知骨架（N1）

- [ ] **N1**：评论通知骨架
  - CommentCreated 事件已有
  - 新增 notification-consumer 骨架：消费 CommentCreated → 生成通知 payload（帖主 / 被回复人）→ 发布到 notification 域
  - V1 仅骨架代码，推送渠道由 notification 域承接

### Phase 8：测试与门禁（T1~T6）

- [ ] **T1**：T1 契约测试 — CommentDto 字段 ↔ metadata fields.yaml；API 路径 ↔ service.yaml
- [ ] **T2**：T2 交互测试 — 8 入口打开弹窗 → 加载 → 提交 → 列表更新 → 点赞 → 删除（Mock 模式）；排序切换；回复折叠/展开；长评论折叠/展开
- [ ] **T3**：T3 端云联调测试 — Remote Repository 与 Go Handler 路径/参数/响应一致
- [ ] **T4**：云侧 contract_test — comment_thread（CRUD + 分页 + 热评排序 + 点赞），Go 测试用嵌入式 MongoDB
- [ ] **T5**：错误码契约测试 — `python3 scripts/verify_error_code_semantic.py` 通过；comment_too_long / comment_rate_limited / comment_like_duplicate 均由 errors.yaml 驱动
- [ ] **T6**：CommentProvider 单元测试 — 乐观更新状态机（sending → confirmed / retry / rollback）、分页、排序切换
- [ ] `make gate` + `make gate-full` 通过

### Phase 9：端云不一致修复（X1~X3，随本特性一并修复）

- [ ] **X1**：chatVideo 时长 Dart 600s → 300s，对齐 Go 侧（`upload_policy.dart`）
- [ ] **X2**：RTC cache TTL 代码 3600s → 60s，对齐 metadata（`call_state_cache.go`）
- [ ] **X3**：评论字数限制 Go Handler 增加 max_length 校验（在 S6 中完成）

---

## 搁置任务（带规划）

| 任务 | 搁置原因 | 重启条件 | 承接节点 |
|------|---------|---------|---------|
| 审核流水线（F15/A21） | 待运营系统统一规划 | 运营系统设计完成 | ops 域新节点 |
| 图片/视频评论 | V1 仅文本 | V3 迭代 | comment-thread V3 |
| 评论置顶 | 需权限体系完善 | V2 | comment-thread V2 |
| 评论搜索 | 需 ES 基础设施 | V2+ | 新建 L4 节点 |
| IP 属地显示 | 需政策配合 | V2 | comment-thread V2 |
| 评论区关闭 | 需帖子权限扩展 | V2 | comment-thread V2 |
| 敏感词前置拦截 | V1 先发后审 | V2 审核增强 | ops 域 |

---

## 未来演进任务

| 演进方向 | 与 design 对应 | 触发条件 |
|---------|---------------|---------|
| 超热帖 ZSet 分片 | design §九 | 单帖 >10 万 + QPS >1 万 |
| 二级分页（主评论+回复独立游标） | design §九 | 单帖回复 >1 万 |
| WebSocket 实时推送新评论 | design §九 | realtime 域就绪 |
| 表情评论（V2） | spec §三 | UI 基础组件就绪 |
| 图片评论（V3） | spec §三 | 审核能力增强 |
| App Config WebSocket 热更新 | design §6.7 | realtime 域就绪 |
| 审核流水线 | design §八 | 运营系统规划完成 |
