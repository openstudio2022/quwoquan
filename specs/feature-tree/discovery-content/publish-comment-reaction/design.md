# 设计说明：publish-comment-reaction（L2）

> 版本：V1 — 2026-07-20（随 comment-thread V4 规格冻结落笔；替代原规划占位）

## 设计动因

发布、评论与反应是内容消费旅程的互动闭环。本能力的设计要同时满足：对象化 DDD 边界（Comment / ContentReaction / Post / Report 各自独立聚合）、监管合规（评论治理与 IP 属地）、业界体验基线（热评排序、通知矩阵）与趣我圈交集差异化（关系标签事实投影），并保证四环境可验证。

## 对象协作与状态机

### 对象关系

```
Post 1--N Comment（postId 引用，无聚合内嵌）
Comment 1--N Comment（两级线程，parentCommentId 归一到一级根）
Comment N--N MediaAsset（attachmentMediaIds，绑定已验证引用）
ContentReaction: persona × (post|comment) 的三态互斥关系（like/dislike/none）
Report: target ∈ {post, comment}，处置结果驱动治理命令
persona_follow_projection: user 域关注事实在 content 域的只读投影（既有），供 viewerRelation 批量判定
```

### 写文字发布状态机

写文字不是独立聚合；micro/article 继续共用 `Post`。端云协作固定为：

```text
LocalPostDraft
  -> immutable PostPublicationIntent
  -> length/rate/safety admission
  -> Post(published) + PostPublicationReceipt + PostPublished outbox
  -> detail/work-browser + feed/persona-work invalidation
```

- `LocalPostDraft` 和 retry/blocked intent 只存在端侧 typed store。
- Post 不承载远端草稿；`pending_review` 是用户已提交、不可编辑且不可公开的 revision。
- Post 状态闭集为 `pending_review/published/rejected/deleted`；机器 allow 可直接
  published，review/unavailable 必须 pending_review，人工决定后进入 published/rejected。
- `PostModerationCase` 的内部领取态 `reviewed` 必须进入枚举闭集，不能让 fields 状态机
  与 generated type 漂移。

### 发布前准入端口

Post application 依赖两个对象专属 domain port：

1. `PublicationRateGate`：以 Persona + 时间窗口原子判定发布额度，生产使用 Redis
   adapter；依赖故障 fail-closed。
2. `PublicationSafetyGate`：输入规范化后的标题、正文/Markdown、mention 和媒体类型，
   返回 `allow/review/reject/unavailable`。生产 composition 必须显式注入；alpha/test 使用
   确定性 adapter，禁止 Remote 失败后降级为 allow。

顺序是 payload 结构/长度校验 → rate gate → safety gate → 事务提交。review/unavailable
提交 pending_review 并发出 durable review fact；幂等重放先回读既有 receipt，避免已提交
intent 被再次扣减额度或重复审核。

### 发布结果与任务读模型

- App 端 `PostPublicationIntentQueueState` 是 submitting/retry_wait/blocked/accepted 的
  typed projection，并提供 retry/discard command。
- pending_review receipt 保留草稿快照并进入任务中心；只有状态变为 published 才清理草稿，
  rejected 可复制为新草稿修改后产生新 intent。
- micro 成功进入内容详情，article 进入作品浏览器；回读失败只重试 query，不重复 command。
- Circle placement 在 Post receipt 后执行，失败只保留未完成 circleId，不重复创建 Post。

### 创作发布可观测

创作是产品 Journey，不是推荐行为。App 通过 ops event catalog 的
`content_publication` 强类型事件记录 editor/draft/submit/queued/blocked/published 阶段；
服务侧继续由 HTTP RED 和 `content_post_publication_submit` 记录 operation SLI。两条轨道
用脱敏 correlation hash 对账，禁止记录正文、标题、原始 intent id 或 user id。

### 图片编辑会话与媒体交接

图片编辑是发布前的 App runtime session，不是 Post 子对象，也不创建云端草稿或动态
编辑参数字段：

```text
local.image_edit_session
  -> ImageEditorExportEngine（确认即烘焙）
  -> CreateMediaItem(localPath)
  -> MediaUploadSession
  -> MediaAsset
  -> PostPublicationIntent(mediaAssetIds)
```

- `ImageEditorExportEngine` 是裁剪、旋转/翻转、颜色矩阵、局部径向调整、曲线、
  马赛克和文字合成的唯一像素真相源；页面只负责交互状态和参数映射。
- 每次工具确认生成一个本地文件快照并写入 `ImageEditorStepStack`；undo/redo 仅切换
  已验证路径，不重算历史。返回时有修改必须显式确认放弃。
- `local.image_edit_session` 生命周期严格绑定单个 `ImageEditorPage`，不跨页面共享、
  不持久化、不发云命令，因此由页面状态 + 强类型 `ImageEditorStepStack` 持有；禁止为此
  新建全局 Riverpod Notifier，避免把瞬时手势态扩散成第二状态源。
- 编辑器不拥有上传、对象存储、处理状态或公开 URL；点击完成后才把本地路径交给
  `ContentMediaUploadCoordinator`，云端只认 `MediaAsset` 业务 ID。
- 页面生命周期与工具提交进入产品遥测；不把本地编辑动作伪装为推荐行为事实。
- FilterCatalogRelease、图片 variants 和 EditRecipe/FilterUsageFact 是独立 Story 的
  云端对象，必须 metadata-first，不得把动态 Map 或 App asset 继续当业务真相源。

### 滤镜目录发布与端侧副本

`FilterCatalogRelease` 位于 `content.media` bounded context，是包含有界分类、预设和
强类型 15 项调整参数的一次不可变发布：

```text
canonical catalog artifact
  -> StageFilterCatalogRelease
  -> ActivateFilterCatalogRelease
  -> ActiveFilterCatalogReader
  -> generated operation client
  -> FilterCatalogCoordinator
       -> VerifiedFilterCatalogStore
       -> generated bootstrap replica
  -> ImageEditorPage
```

- Stage 后目录内容不可变；Activate 以单事务把旧 active 置为 retired，再把目标置为
  active。Rollback 只允许 retired 目标重新激活，禁止修改历史发布内容。
- Data publish plane 是唯一写入口；App 只读取 active release，不发送目录写命令。
- Remote adapter 只做 typed 映射；coordinator 负责 schema/摘要/引用/范围校验和本地
  verified cache 原子替换，页面不得直接读网络、文件或 asset。
- 原 `assets/filters/filter_presets.json` 必须由 canonical release artifact 生成
  bootstrap replica 并带 `releaseId + canonicalDigest`；它是可验证复制品，不是第二
  业务真相源。手写空目录、任意参数 Map 和 Remote 失败返回伪成功均禁止。
- 像素执行仍由 `ImageEditorExportEngine` 完成；目录只提供预设参数，不能形成第二像素
  管线。
- 详细状态机、SLO、四环境与验收见
  `filter-catalog-release/spec.md`、`filter-catalog-release/acceptance.yaml`。

### Comment 状态机（V4）

`active →(作者 CAS 软删) deleted`；`active →(operator HideComment) hidden →(operator RestoreComment) active`；`active|hidden →(PostDeleted 级联) tombstoned`。deleted/tombstoned 为终态。前台列表只读 active；「我的评论」向作者展示 hidden 状态标记；计数排除非 active。

### 排序与 hotScore 投影

- 一级评论两档服务端排序：`hot`（默认）与 `latest`；置顶段永远在前。
- `hotScore = (likeCount - dislikeCount) + 2 * replyCount`，由独立 relay 消费 `ContentReactionSet/Cleared`、`CommentCreated/Deleted/Moderated(reply)` 事实触发权威数据重算，落 `comments` 集合字段并走复合索引；可全量重算，无 Redis 排行、无 `$inc` 重放漂移、无 batch 衰减（演进项）。
- 事实链：reaction/reply 事实 → hotScore relay → comments.hotScore → keyset 索引 → CommentPageSlice。排序永远是服务端单一真相源。

### 治理链路

举报（Report target=comment，既有 Report Facade）→ operator 处置（ResolveReport）→ `HideComment/RestoreComment`（operator principal，`content.moderation.*` 权限）→ `CommentModerated` outbox 审计事实。评论不建 per-comment 审核 Case（区别于 PostModerationCase 的先审后发场景）：评论是高频 UGC，采用「先发后审 + 举报驱动 + 频控」组合，机审接入为演进项。

### 展示投影（读模型组合器）

`CommentPageSlice` 组合五个事实源，全部批量读取避免 N+1：

| 投影字段 | 事实源 | 语义 |
|---|---|---|
| `viewerReaction/likeCount/dislikeCount` | content_reactions | 既有 |
| `replyCount/replyPreview` | comments 子查询 | 既有 |
| `capabilities` | Comment + Post ownership | 既有 |
| `authorIpLocation` | Comment 创建时快照 | 新增；创建时经受信代理头解析，读路径透传 |
| `authorLiked` | content_reactions（subject=Post 作者） | 新增；作者赞过事实 |
| `viewerRelation` | persona_follow_projection | 新增；none/following/friend（互关），viewer 未登录恒 none |

### 通知矩阵

| 事实 | 接收者 | 通知 |
|---|---|---|
| CommentCreated（一级） | Post 作者 | 新的评论（既有） |
| CommentCreated（回复） | replyToUserId | 新的回复（既有） |
| CommentCreated.mentionedUserIds | 被 @ 用户 | @ 提及（V4 新增） |
| CommentPinChanged(isPinned=true) | 评论作者 | 你的评论被置顶（V4 新增） |

自评/自回/自 @ 跳过；通知项点击经评论深链（`MediaViewerCommentContext`）回到原评论定位。

## 端侧结构

- 统一评论组件族（`lib/ui/content/comments/**`）三宿主复用（cardModal/immersiveSplit/profileInteraction），不复制状态机。
- typed Facet：`ContentCommentQuery/CommandWriter/ReactionWriter`（pure contracts）；production Remote-only。
- 行为回流：评论创建成功后 `trackComment`（BehaviorAction.comment，含 commentLength/feedRequestId/referralSource）→ 推荐 HotPath。
- @ 候选：消费 user 域 typed relationship Facet（我的关注），不引入第二套联系人模型。

## 非功能

- SLO：列表 P95 800ms / 回复与命令 P95 500ms；hotScore 投影收敛滞后 SLI + 告警。
- 频控：CreateComment 在聚合提交事务内通过 `comment_author_rate_limit_locks` 按 authorId 串行化，再按 `idx_comments_author_rate_window` 对短窗/日窗做权威 count；检查、Comment、receipt 与 outbox 同事务提交，避免多实例并发超卖，阈值由 config.yaml 驱动。
- 属地：alpha 使用确定性 resolver；beta/gamma/prod 只装配固定版本、双 SHA256 校验的 ip2region IPv4+IPv6 离线库。境内投影到省级、境外投影到国家级，原始 IP 不落 Comment/日志；缺库或数据超过 45 天启动失败，lookup outcome 与 data age 进入 Prometheus 告警。
- 弱网：追加失败仅尾部重试、已有数据刷新失败保留旧数据；命令失败保留草稿。
- 灰度：Canary → 1% → 50% → 100%，回滚条件绑定评论创建成功率与列表可用性 SLO。

## 与既有规则关系

- R-CMT01 教训固化：排序/计数权威化在 Mongo 复合索引，禁止只写不读的 Redis 排行。
- 交集表达遵守「可证实事实」纪律：viewerRelation/authorLiked 均为事实投影，无事实不显示；禁止把推荐相似度伪装为关系标签。
- 存量三档排序符号（`recommended/latest/most_liked`）禁止回归；`sort` 参数只接受 `hot|latest`。

## 未来演进

- hotScore 时间衰减与个性化热评（需先冻结确定性基线并积累互动数据）。
- `same_circle` 关系标签（圈子成员批量交集判定成本评估后排期）。
- 机审接入（文本/图片审核供应商）与 shadow-ban 语义。
- 评论搜索与翻译。
