# L3 特性：comment-thread（Comment / ContentReaction 商用对象闭环）

> 版本：V3 — 2026-07-14
> 归属：`discovery-content / publish-comment-reaction / comment-thread`
> 架构约束：受 `runtime/system-architecture-and-engineering-guide/app-cloud-business-object-commercial-closure` 统一约束

## 1. 目标与用户价值

为图片、视频、微趣和文章提供同一套二层评论体验。用户可以读取一级评论与回复、发表和删除评论、赞/踩、回复、附图、@、置顶并从互动页回到原评论；所有页面都消费 Comment 与 ContentReaction 的服务端权威投影，不维护端侧业务对象副本或第二套排序规则。

## 2. 领域边界

### 2.1 对象所有权

| 对象 | Command owner | Query owner | 权威存储 | 事务边界 |
|---|---|---|---|---|
| `Comment` | `CommentCommandFacade` | `CommentQueryFacade` | MongoDB `comments` | Comment aggregate + outbox |
| `ContentReaction(comment)` | `CommentReactionCommandFacade` | Comment 商用投影组合器 | MongoDB `content_reactions` | ContentReaction aggregate + outbox |
| `Post` | `PostCommandFacade` | `PostQueryFacade` | MongoDB `posts` | 只提供目标存在性、ownership 与计数投影 |
| `MediaAsset` | Media Facade | `CommentAttachmentReader` | Media 权威存储 | Comment 只绑定已验证 media id |

`PostService`、聚合 `ContentRepository`、动态 `Map` DTO、UI 自算权限和本地排序都不是 Comment 主线。Data importer、Ops 和页面不得直写 `comments`、reaction 或 Post 计数投影。

### 2.2 层级与顺序

- 仅支持两级：一级 Comment 与一级 Comment 下的回复；回复目标可指向回复，但 `parentCommentId` 必须归一到一级 Comment。
- 一级列表唯一顺序为 `isPinned desc, pinnedAt desc, createdAt desc, id desc`。
- 回复唯一顺序为 `createdAt asc, id asc`。
- 不提供 `recommended/latest/most_liked` 兼容参数、别名或端侧切换器。
- 分页只使用服务端 opaque cursor；禁止 offset 深翻页和端侧重排。

## 3. 功能规格

| 编号 | 能力 | 规格 |
|---|---|---|
| F1 | 一级评论 | 首屏与追加页返回 typed `CommentPageSlice`，默认 20 条。 |
| F2 | 回复 | 一级项携带 `replyCount/replyPreview/replyNextCursor`；展开使用 typed `ReplyPageSlice`。 |
| F3 | 创建 | 命令携带正文、reply target、media ids、typed mentions 与 persona 快照；必须有 actor 和幂等键。 |
| F4 | 删除 | 作者使用 aggregate version 做 CAS 软删除；陈旧 version 返回稳定冲突错误。 |
| F5 | 赞踩 | `like/dislike/none` 三态互斥；服务端返回精确计数，列表重入以 `viewerReaction` 为准。 |
| F6 | 置顶 | 仅 Post owner 可置顶未删除的一级 Comment；pin/unpin 使用 aggregate version。 |
| F7 | 附件 | Comment 只持有 media id；查询投影返回 typed attachment 与 available 状态。 |
| F8 | @ | 输入、登录续接、command 全程使用 `ContentCommentMention`，不转换为 UI wire map。 |
| F9 | 登录续接 | 保留 post、reply target、正文、附件和 mentions；目标不一致时不得误提交。 |
| F10 | 个人互动 | “我的评论”“收到的评论”和互动深链使用 typed Facet，携带 post/comment/parent identity。 |
| F11 | 权限投影 | `isAuthor/canDelete/canReply/canReport/canPin` 由 Service 派生，App 只渲染。 |
| F12 | 计数 | Comment count 的权威值来自 Comment reader；Post 计数是可修复投影，不是第二真相源。 |

## 4. 端云接口

### 4.1 Service

- Go 只暴露对象专属 `CommentCommandFacade`、`CommentQueryFacade`、`CommentAggregateStore`、具名 Reader 和 typed Slice。
- Comment commit 必须把 aggregate 与 outbox event 原子写入；dispatcher 使用 checkpoint、重试和 replay-safe delivery。
- 查询组合 Comment、ContentReaction、Post ownership、MediaAsset；任何必要依赖失败都 fail closed，不返回默认零值伪成功。
- HTTP handler 只把 generated operation 转为 typed command/query；业务 command 不携带 operation id、route、surface 或 actor metadata。

### 4.2 App

- pure contracts 定义 command/result/Slice/`ContentCommentMention`/`ContentCommentAttachment`。
- production 只装配 `RemoteContentCommentFacet`，且只调用 generated operation client。
- alpha 只在独立 runner 装配 `AlphaContentCommentFacet`；production kernel 不可达 mock/fixture。
- `CommentNotifier` 在 command 成功后强制读取权威投影；不得构造一个字段不完整的乐观 Comment。
- Runtime failure、401 refresh、429/deadline/retry 和 telemetry 走统一 Runtime execution path。

## 5. 页面与体验

- Feed、沉浸式作品、文章详情、图片/视频查看器和个人互动页复用同一 Comment surface/facet，不复制状态机。
- 评论项展示作者快照、正文、时间、回复摘要、赞踩、附件、权限动作和置顶状态。
- 评论总数只有在已确认时展示；首屏阻塞失败显示“评论”，不得把未知总数伪装成“共 0 条评论”。
- 输入支持 emoji、图片和 @；失败保留草稿并提供显式恢复动作，不静默切换 Mock 或伪造成功。
- light/dark、多屏、无障碍、键盘、弱网和返回恢复由 UAT 验证。

## 6. 一致性、安全与性能

- Command 必须有 authenticated persona actor、Idempotency-Key 和需要时的 expected version。
- 相同 actor + idempotency key + digest 重放返回原 receipt；不同 digest 返回稳定 idempotency conflict。
- Comment 与 outbox 原子；ContentReaction 与 outbox 原子；投影消费者按 event id 去重。
- 一级/回复 keyset 查询必须命中声明索引，无 `COLLSCAN` 和阻塞排序。
- 目标：列表 P95 < 800ms，回复 P95 < 500ms，命令确认 P95 < 500ms。
- 指标至少覆盖 list/append/command latency、version conflict、idempotency replay、outbox lag/retry/DLQ、projection convergence 与 UI recovery。

## 7. 测试证据

- `local_contract`：aggregate 不变量、typed codec、严格 decoder、能力投影、RuntimeFailure、alpha/Remote parity、安全负例。
- `api_integration`：真实 HTTP、Mongo、outbox、reaction、pin、keyset 索引与计数收敛；禁止 Memory、自 seed 和动态 skip。
- `user_acceptance`：真实页面执行评论、回复、赞踩、置顶、登录续接、深链与恢复；文件存在性不算 UAT。

## 8. Out of Scope

- 评论全文搜索、翻译、视频附件与 ML rerank。
- 通用 CRUD Repository、Event Sourcing 框架或跨对象 Saga 平台。
- IP 属地与“作者赞过”展示；未形成 metadata、服务投影和三层证据前不得以旧 DTO 字段保留。
- 历史 `CommentDto`、`CommentPage`、`ContentCommentRepository`、三档排序和失败回退 Mock 的任何兼容。

## 9. 准出条件

仅当 metadata/codegen、Comment/ContentReaction Facade、Mongo/outbox、production Remote-only、alpha 隔离、三层证据、Gamma UAT、观测/告警/runbook 和相关门禁都通过时，本 Story 才能整体准出。未验证环境或 Journey 必须保持 `GATE_BLOCK`。
