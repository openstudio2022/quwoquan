# L3 Story：interaction-notification-inbox

## 最小价值点

用户产生的核心互动（评论/回复、点赞、关注、帖子被引用、圈子成员加入、圈内群申请与审批、打招呼）由业务事件驱动生成持久化 AppMessage 通知，用户在消息页`通知`维度看到真实通知行、可点击跳转到目标对象并推进已读，未读数在消息 tab 徽标一致呈现。App 不猜测、不拼接、不轮询业务对象。

## 归属

- 领域服务：`chat-conversation`
- 业务能力：`commercial-message-system`
- 关联 Journey / Scenario：`message-direct-and-greeting-upgrade`（消息页通知维度）

## 行为范围

### In Scope

- 七个事件源 → AppMessage 的服务端投影规则（触发矩阵、接收者、幂等、过滤）。
- 消息页`通知`维度的行渲染、点击跳转、已读推进与未读徽标。
- 通知维度曝光/点击/已读行为埋点。

### Out of Scope

- push 外送（APNs/FCM provider、设备 token 注册、投递回执）：显式降级站内信，`push_delivery` 契约保留标 deferred；`NotificationDeliveryJob` 三条运维路由保持 blocked。
- 通知聚合/折叠（"N 人赞了你"）：V1 不做，逐事件一行。
- 聊天消息未读（由 conversation read watermark 承载，不进 AppMessage）。
- 打招呼收件箱升级流程（由 `greeting-request-inbox-and-upgrade` story 承载；本 story 只生成"收到打招呼"通知行）。

## 七源触发矩阵（唯一真相源）

| # | 业务事件 | 事件源文件 | 接收者 | messageType | source | 不通知条件 |
|---|---|---|---|---|---|---|
| 1 | CommentCreated | `content/comment/events.yaml` | 顶级评论→postAuthorId；回复→replyToUserId | content | comment | 接收者==actorId（自评/自回复） |
| 2 | ContentReactionSet | `content/content_reaction/events.yaml` | targetAuthorId | content | reaction | 接收者==actorId；ContentReactionCleared 不通知 |
| 3 | PostPublished（sourcePostId 非空的引用发布） | `content/post/events.yaml` | sourcePostAuthorId | content | post_quote | sourcePostId 为空（普通发布）；接收者==authorId（自引用） |
| 4 | PersonaFollowStateChanged | `user/persona_relationship/events.yaml` | targetPersonaId | social | follow | following==false（取关）不通知 |
| 5 | GreetingRequestSent | `user/greeting_request/events.yaml` | targetSubAccountId | social | greeting | 按既有 side_effects 条件 `targetUser.allowStrangerGreeting == true` 才通知 |
| 6 | CircleMembershipJoined | `social/circle_membership/events.yaml` | 圈主（circle owner） | circle | circle_member | 接收者==加入者本人 |
| 7 | CircleGroupMembershipRequested / Activated / Rejected | `social/circle_group_membership/events.yaml` | Requested→群管理员；Activated/Rejected→申请者 | circle | circle_group | 审批者==申请者本人 |

矩阵约束：

- messageType 只使用既有 `NotificationType` 枚举五大类（content/social/circle/system/assistant），互动细分由 `source` 字段承载；不扩枚举。
- 事件 payload 必须自包含接收者：`CommentCreated` 补 `postAuthorId`、`ContentReactionSet` 补 `targetAuthorId`（metadata-first 扩 payload_fields）；消费者不得跨服务反查写模型。
- 幂等键固定 `notify:{eventType}:{eventId}`（eventId 取事件唯一标识：commentId/reactionId/pairId 等），事件重放不产生重复通知；CreateAppMessage 的 `idempotencyKey` 唯一索引兜底。
- 事件消费经 durable Redis Stream consumer group（Mongo inbox 幂等 + 失败计数 DLQ），不使用 fire-and-forget Pub/Sub。

## 通知行与未读语义

- `通知`维度数据只来自 `ListAppMessages`（云端 inbox），行渲染 title/summary/时间/已读态；点击按 `target`（targetType/targetId/routeId/routePath）真实路由跳转，并调用 `ReadAppMessage` 推进已读。
- 消息 tab 徽标未读数来自 `GetAppMessageUnreadCount`，与通知行已读推进同步失效刷新。
- 无通知数据时通知维度展示独立空态，不回退拼接。

## 接口契约

- API path / operation：`CreateAppMessage`（service principal）、`ListAppMessages`、`GetAppMessage`、`AckAppMessage`、`ReadAppMessage`、`GetAppMessageUnreadCount`（`notification/notification/service.yaml`）。
- DTO / projection：`AppMessage`、`AppMessageInboxSlice`、`AppMessageUnreadCountSlice`。
- error code：`NOTIFICATION.*`（notification errors.yaml，端侧经 codegen 枚举消费）。
- surface / route：消息页 surface（chatList）绑定 AppMessage 读操作；通知行跳转 route 来自 metadata target。

## 验收关注点

- done_when：七源事件在真实存储链路（Redis Stream + Mongo）生成一次且仅一次 AppMessage；通知行可点击跳转并推进已读；未读徽标一致；自互动/取关/清除不产生通知。
- edge cases：事件重放、消费者崩溃续作（pending claim）、接收者与行动者同人、通知目标对象已删除（跳转降级到结构化空态）、无通知空态。
- test evidence：`local_contract`（投影规则/幂等/过滤 + 端侧 widget/provider）、`api_integration`（事件 → inbox → unread → read 全链）、`user_acceptance`（消息页通知维度旅程）。
