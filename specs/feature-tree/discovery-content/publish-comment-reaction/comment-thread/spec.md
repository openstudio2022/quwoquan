# L3 特性：comment-thread（Comment / ContentReaction 商用对象闭环）

> 版本：V4 — 2026-07-20（V3 基线之上的商用补齐；V3 架构骨架不变）
> 归属：`discovery-content / publish-comment-reaction / comment-thread`
> 架构约束：受 `runtime/system-architecture-and-engineering-guide/app-cloud-business-object-commercial-closure` 统一约束

## 0. V4 变更记录（决策依据）

V4 在 V3（2026-07-14 零兼容重做：独立聚合、Mongo+outbox、typed Facet、production Remote-only）骨架不变的前提下，收编三类商用缺口。业界对标（小红书 / 抖音 / B站评论区，检索日期 2026-07-20）与监管合规是变更依据：

| 变更 | V3 口径 | V4 口径 | 依据 |
|---|---|---|---|
| 排序 | pinned-first 唯一顺序，App 不传 sort | `sort=hot\|latest` 两档，默认 `hot`；服务端 hotScore 单一真相源 | 三家标杆默认热评序；两档≠旧三档（无 recommended 模型档、无端侧重排） |
| 生命周期 | `active/deleted` 两态 | `active/hidden/deleted/tombstoned` 四态 + 治理命令 | 《网络跟帖评论服务管理规定》要求审核管理、实时巡查、应急处置能力 |
| IP 属地 | Out of Scope | `authorIpLocation` 创建时快照，服务端解析 | 《互联网用户账号信息管理规定》展示 IP 属地要求；三家标杆均有 |
| 作者赞过 | Out of Scope | `authorLiked` 服务端投影 | 小红书「作者赞过」、B站「UP 觉得很赞」 |
| 交集标签 | 无 | `viewerRelation`（none/following/friend）服务端投影 | 趣我圈交集差异化：可证实关系事实，非推荐推断；B站「好友点赞」同型 |
| 频控 | 错误码有声明无实现 | CreateComment 业务频控落地 | comment_rate_limited 已在 errors.yaml，实现补齐 |
| Post 删除级联 | 无处置 | PostDeleted → 评论批量 tombstone | 对象生命周期同步 |
| 通知 | 仅评论/回复 | 补 @提及、置顶通知 | 三家标杆通知矩阵标配 |

## 1. 目标与用户价值

为图片、视频、微趣和文章提供同一套二层评论体验。用户可以读取一级评论与回复、发表和删除评论、赞/踩、回复、附图、@、置顶、举报，按热度或时间浏览，看到评论者 IP 属地、作者互动标记与自己和评论者的关系标签，并从互动页和通知回到原评论；所有页面都消费 Comment 与 ContentReaction 的服务端权威投影，不维护端侧业务对象副本或第二套排序规则。

## 2. 领域边界

### 2.1 对象所有权

| 对象 | Command owner | Query owner | 权威存储 | 事务边界 |
|---|---|---|---|---|
| `Comment` | `CommentCommandFacade` | `CommentQueryFacade` | MongoDB `comments` | Comment aggregate + outbox |
| `ContentReaction(comment)` | `CommentReactionCommandFacade` | Comment 商用投影组合器 | MongoDB `content_reactions` | ContentReaction aggregate + outbox |
| `Post` | `PostCommandFacade` | `PostQueryFacade` | MongoDB `posts` | 只提供目标存在性、ownership 与计数投影 |
| `MediaAsset` | Media Facade | `CommentAttachmentReader` | Media 权威存储 | Comment 只绑定已验证 media id |
| `Report(target=comment)` | Report Facade（既有） | Report Facade | Report 权威存储 | 评论级举报走既有 Report 对象，不新建评论侧举报模型 |

`PostService`、聚合 `ContentRepository`、动态 `Map` DTO、UI 自算权限和本地排序都不是 Comment 主线。Data importer、Ops 和页面不得直写 `comments`、reaction 或 Post 计数投影。

### 2.2 生命周期（V4 状态机）

```
active --作者删除--> deleted（软删，终态）
active --治理隐藏（operator）--> hidden
hidden --治理恢复（operator）--> active
active/hidden --PostDeleted 级联--> tombstoned（终态）
```

- `hidden`：治理隐藏，前台一律不可见；作者在「我的评论」中可见状态标记；仅 operator 可恢复。
- `tombstoned`：宿主 Post 删除后的级联终态，前台不可见，保留审计事实；不可恢复。
- `deleted` 保持 V3 语义（作者触发、服务端内部 CAS 的软删）。
- 状态迁移只允许上述边；任何非法迁移返回稳定 conflict 错误。

### 2.3 层级与顺序

- 仅支持两级：一级 Comment 与一级 Comment 下的回复；回复目标可指向回复，但 `parentCommentId` 必须归一到一级 Comment。
- 一级列表支持两档服务端排序，App 只能传 `sort=hot|latest`，默认 `hot`：
  - `hot`：`isPinned desc, pinnedAt desc, hotScore desc, createdAt desc, id desc`
  - `latest`：`isPinned desc, pinnedAt desc, createdAt desc, id desc`
- `hotScore` 是由 ContentReactionSet/Cleared 与 CommentCreated/CommentDeleted/CommentModerated(reply) 事实驱动的确定性投影分：`hotScore = (likeCount - dislikeCount) + 2 * replyCount`，落库于 comments 集合并走复合索引；可随时从权威数据重算。无互动时全部同分，hot 档自然退化为 latest 行为。
- 回复唯一顺序为 `createdAt asc, id asc`。
- 禁止恢复旧三档 `recommended/latest/most_liked` 命名与语义；禁止端侧重排；禁止 Redis ZSet 排行第二真相源（R-CMT01 教训）。
- 分页只使用服务端 opaque cursor；禁止 offset 深翻页。

## 3. 功能规格

| 编号 | 能力 | 规格 |
|---|---|---|
| F1 | 一级评论 | 首屏与追加页返回 typed `CommentPageSlice`，默认 20 条；`sort=hot\|latest` 两档。 |
| F2 | 回复 | 一级项携带 `replyCount/replyPreview/replyNextCursor`；展开使用 typed `ReplyPageSlice`。 |
| F3 | 创建 | 命令携带正文、reply target、media ids、typed mentions 与 persona 快照；必须有 actor 和幂等键；服务端捕获客户端 IP 解析 `authorIpLocation` 快照（解析不出为空、不展示，绝不臆造）。 |
| F4 | 删除 | 作者提交命名删除意图；服务端以内部 CAS 和有界重放完成软删，重复意图按幂等 receipt 返回原结果，不向调用方公开 aggregate version。 |
| F5 | 赞踩 | `like/dislike/none` 三态互斥；服务端返回精确计数，列表重入以 `viewerReaction` 为准。 |
| F6 | 置顶 | 仅 Post owner 可置顶未删除的一级 Comment；pin/unpin 以服务端内部 CAS 的命名状态迁移执行，置顶变更通知评论作者。 |
| F7 | 附件 | Comment 只持有 media id；`attachmentMediaIds` 至多 9 个，创建和后绑定均在服务端拒绝超限并返回 `comment_attachment_limit_exceeded`；查询投影返回 typed attachment 与 available 状态。后绑定是命名状态迁移，由服务端内部 CAS 有界重放，调用方不携带 aggregate version。 |
| F8 | @ | 输入、登录续接、command 全程使用 `ContentCommentMention`；候选来自我的关注（typed relationship Facet），被 @ 用户收到通知。 |
| F9 | 登录续接 | 保留 post、reply target、正文、附件和 mentions；目标不一致时不得误提交。 |
| F10 | 个人互动 | “我的评论”“收到的评论”和互动深链使用 typed Facet，携带 post/comment/parent identity；「我的评论」可见 hidden 状态标记。 |
| F11 | 权限投影 | `isAuthor/canDelete/canReply/canReport/canPin` 由 Service 派生，App 只渲染。 |
| F12 | 计数 | Comment count 的权威值来自 Comment reader；Post 计数是可修复投影，不是第二真相源；count 排除 hidden/deleted/tombstoned。 |
| F13 | 举报 | 评论长按/更多菜单提交 Report(target=comment)；处置（ResolveReport）驱动治理命令。 |
| F14 | 治理 | `HideComment/RestoreComment` 仅 operator（`content.moderation.*` 权限）可执行；产生 `CommentModerated` 审计事实。 |
| F15 | 频控 | CreateComment 按 authorId 滑动窗口频控（配置驱动，默认 30s ≤ 5 条且 24h ≤ 200 条），超限返回 `comment_rate_limited`。 |
| F16 | 展示投影 | 列表项携带 `authorIpLocation`、`authorLiked`（Post 作者赞过事实）、`viewerRelation`（viewer 对评论作者：none/following/friend，来自 persona_follow_projection 事实），批量读取避免 N+1。 |
| F17 | 级联 | PostDeleted 事实驱动该 Post 全部评论批量 `tombstoned`；投影计数同步归零。 |
| F18 | 行为回流 | 端侧评论创建成功后经 `trackComment` 上报行为信号（含 commentLength/feedRequestId/referralSource），进入推荐 HotPath（云侧 weight 2.5 已就绪）。 |

## 4. 端云接口

### 4.1 Service

- Go 只暴露对象专属 `CommentCommandFacade`、`CommentQueryFacade`、`CommentAggregateStore`、具名 Reader 和 typed Slice；治理命令挂 `CommentCommandFacade`（operator principal）。
- Comment commit 必须把 aggregate 与 outbox event 原子写入；dispatcher 使用 checkpoint、重试和 replay-safe delivery。
- hotScore 投影由独立 relay 消费 reaction/comment 事实增量更新，可全量重算；不引入 Redis 排行、批处理衰减（衰减列入演进方向）。
- 查询组合 Comment、ContentReaction、Post ownership、MediaAsset、persona_follow_projection；任何必要依赖失败都 fail closed，不返回默认零值伪成功。
- HTTP handler 只把 generated operation 转为 typed command/query；从受信代理头解析客户端 IP 注入 context（复用 `ParseTrustedClientIP`）。

### 4.2 App

- pure contracts 定义 command/result/Slice/`ContentCommentMention`/`ContentCommentAttachment`，扩展 `authorIpLocation/authorLiked/viewerRelation/sort` 强类型字段。
- production 只装配 `RemoteContentCommentFacet`，且只调用 generated operation client。
- alpha 只在独立 runner 装配 `AlphaContentCommentFacet`；production kernel 不可达 mock/fixture。
- `CommentNotifier` 在 command 成功后强制读取权威投影；不得构造一个字段不完整的乐观 Comment。
- Runtime failure、401 refresh、429/deadline/retry 和 telemetry 走统一 Runtime execution path。

## 5. 页面与体验

- Feed、沉浸式作品、文章详情、图片/视频查看器和个人互动页复用同一 Comment surface/facet，不复制状态机。
- 评论项展示作者快照、正文、时间、IP 属地、回复摘要、赞踩、附件、权限动作、置顶状态、作者赞过标记与关系标签；标签只在事实存在时出现，无事实不显示。
- 排序切换为「热门/最新」两档轻量切换器；切换只重新请求服务端，不做本地重排。
- 长按/更多菜单收敛复制、举报、删除（按权限投影渲染）。
- 通知中心「评论/回复/@/置顶」项点击经既有评论深链（`MediaViewerCommentContext`）回到原评论定位高亮。
- 评论总数只有在已确认时展示；首屏阻塞失败显示“评论”，不得把未知总数伪装成“共 0 条评论”。
- 输入支持 emoji、图片和 @（关注候选选择器）；失败保留草稿并提供显式恢复动作，不静默切换 Mock 或伪造成功。
- light/dark、多屏、无障碍、键盘、弱网和返回恢复由 UAT 验证。

## 6. 一致性、安全与性能

- Comment 的删除、置顶/取消置顶、附件绑定、隐藏和恢复均是命名状态迁移：客户端只提交 authenticated actor 与 Idempotency-Key，服务端读取当前 aggregate version，以内部 CAS 和最多三次纯技术冲突重放完成意图；不得向调用方暴露 `expectedVersion`/`If-Match`。治理命令还必须有 operator actor 与权限校验。
- 相同 actor + idempotency key + digest 重放返回原 receipt；不同 digest 返回稳定 idempotency conflict。
- Comment 与 outbox 原子；ContentReaction 与 outbox 原子；投影消费者按 event id 去重；hotScore 投影收敛滞后有 SLI。
- 一级/回复/热评 keyset 查询必须命中声明索引，无 `COLLSCAN` 和阻塞排序。
- `authorIpLocation` 只在创建时解析落库（快照语义，与业界一致）；境内只展示省/自治区/直辖市，境外只展示国家/地区；读路径不二次解析，原始 IP 不入 Comment、不写日志。
- alpha 使用确定性 fixture resolver；beta/gamma/prod 只允许镜像内固定版本的 ip2region IPv4+IPv6 离线库。缺库、校验失败、错误 provider 或数据版本超过 45 天均启动失败；解析失败落空串。镜像必须固定双库 SHA256、保留许可证，并提供 lookup outcome/data age 指标与告警。
- `viewerRelation/authorLiked` 是服务端事实投影；端侧不得用本地关注缓存拼装关系标签。
- 目标：列表 P95 < 800ms，回复 P95 < 500ms，命令确认 P95 < 500ms。
- 指标至少覆盖 list/append/command latency、version conflict、idempotency replay、outbox lag/retry/DLQ、projection convergence、hotScore 收敛滞后、rate limit 命中、治理动作量与 UI recovery。

## 7. 测试证据

- `local_contract`：aggregate 状态机不变量（含 hidden/tombstoned 迁移与非法迁移拒绝）、typed codec、严格 decoder、能力投影、hotScore 计算、频控窗口、RuntimeFailure、alpha/Remote parity、安全负例（operator 权限、隐藏评论不可见）。
- `api_integration`：真实 HTTP、Mongo、outbox、reaction、pin、两档排序 keyset 索引 explain、PostDeleted 级联、通知投影、计数收敛；禁止 Memory、自 seed 和动态 skip。
- `user_acceptance`：真实页面执行评论、回复、赞踩、置顶、举报、排序切换、登录续接、通知深链与恢复；文件存在性不算 UAT。

## 8. Out of Scope（V4）

- 评论全文搜索、翻译、语音评论、视频附件与 ML rerank。
- hotScore 时间衰减 batch 重算与个性化热评（演进方向，需先冻结确定性基线）。
- `same_circle` 关系标签（需圈子成员批量交集判定，成本评估后单独排期）。
- AI 评论摘要、AI 氛围治理（用户已确认不对标 AI 能力）。
- 通用 CRUD Repository、Event Sourcing 框架或跨对象 Saga 平台。
- 历史 `CommentDto`、`CommentPage`、`ContentCommentRepository`、旧三档排序和失败回退 Mock 的任何兼容。

## 9. 准出条件

仅当 metadata/codegen、Comment/ContentReaction Facade、Mongo/outbox、治理链路、production Remote-only、alpha 隔离、三层证据、Gamma UAT、观测/告警/runbook 和相关门禁都通过时，本 Story 才能整体准出。未验证环境或 Journey 必须保持 `GATE_BLOCK`。
