# L3 Story：互动通知收件箱 (`interaction-notification-inbox`)

> 所属能力：[`commercial-message-system`](../spec.md)

> Journey / Scenario：[`JNY-003 / SCN-008`](../../../spec.md#scn-008)

> 设计归属：[L1 DEC-001](../../design.md#dec-001)

## 1. 用户价值

作为接收互动通知的用户，
我希望按类型查看点赞、评论、关注等通知，并让曝光、点击和已读状态保持一致，
从而快速处理真实互动且不反复看到已读提醒。

## 2. 范围与非目标

### In Scope

- “互动通知收件箱”的输入、可观察主路径、失败语义以及与父能力的交接。
- Gathering invitation 的 typed AppMessage 卡片投影、accept/decline intent 与终态刷新；Participation 事实仍由 Circle 拥有。
- push 外送（APNs/FCM、token 注册、投递回执，显式降级站内信）
- 通知聚合折叠。
- 聊天消息未读（conversation read watermark 承载）

### Out of Scope

- 父能力中由其他 Story 独立拥有的行为、能力级架构决定和实现任务。

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 互动通知收件箱

- 通知曝光、点击与已读事件必须携带同一通知身份；未读徽标必须随服务端已读事实收敛。

<a id="req-002"></a>
### REQ-002 消息页通知维度真实渲染、跳转、已读与未读徽标一致

- 通知曝光、点击与已读事件必须携带同一通知身份；未读徽标必须随服务端已读事实收敛。

<a id="req-003"></a>
### REQ-003 七源触发矩阵与通知契约来源唯一

- 七源事件的 consumers 声明、payload 接收者字段与所属对象 `events.yaml` 的生产者/消费者契约一致。
- messageType 只使用既有 NotificationType 五大类，细分经 source 字段；无第二触发矩阵真相源。
- push 外送尚未完成：`NotificationDeliveryJob` 的受保护路由已生产装配，外部 Provider 终态与真机验收缺口由 `OPEN-001` 明确阻断。

<a id="req-004"></a>
### REQ-004 事件 payload 必须自包含接收者：CommentCreated 补 postAuthorId、ContentReactionSet 补 targetAuthorId（metadata-first 扩 payload_fields）；消费者不得跨服务反查写模型

- 事件 payload 必须自包含接收者：`CommentCreated` 补 `postAuthorId`、`ContentReactionSet` 补 `targetAuthorId`（metadata-first 扩 payload_fields）；消费者不得跨服务反查写模型。

<a id="req-005"></a>
### REQ-005 Gathering invitation 使用 AppMessage 最小既有边界

- Notification 的 AppMessage 收件箱是尚未获得 Gathering room access 的受邀者可见主消息边界；不得为了邀请创建 Chat Conversation、Message 或伪造 ConversationMembership。
- `GatheringInvitationChanged` 经 durable stream 至少一次消费，按 gatheringId+recipient 折叠并以 Participation version/terminal precedence 幂等更新；撤回、取消与 expiresAt 使 action 失效，旧事件不得复活 action。
- 卡片只消费 Circle 自包含的 disclosure-safe typed payload；accept/decline intent 由 App 调用 Circle typed operation，Notification 不反查或写入 GatheringParticipation。

## 4. 契约引用

- canonical：`quwoquan_service/services/notification-service/contracts/notification_delivery/notification/operations.yaml`
- canonical：`quwoquan_service/services/content-service/contracts/content/comment/events.yaml`
- canonical：`quwoquan_service/services/content-service/contracts/content/content_reaction/events.yaml`
- canonical：`quwoquan_service/services/content-service/contracts/content/post/events.yaml`
- canonical：`quwoquan_service/services/user-service/contracts/relationship/persona_relationship/events.yaml`
- canonical：`quwoquan_service/services/user-service/contracts/relationship/greeting_request/events.yaml`
- canonical：`quwoquan_service/services/circle-service/contracts/circle_management/circle_membership/events.yaml`
- canonical：`quwoquan_service/services/circle-service/contracts/circle_management/circle_group_membership/events.yaml`
- canonical：`quwoquan_service/services/circle-service/contracts/circle_management/gathering/events.yaml`
- canonical：`quwoquan_service/services/notification-service/contracts/notification_delivery/notification/fields.yaml`
- canonical：`quwoquan_service/services/notification-service/contracts/notification_delivery/notification/object.yaml`

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 互动通知收件箱

- GIVEN 发起或接收消息的用户具备有效身份，且父能力声明的输入与上游事实成立。
- WHEN 参与者执行“互动通知收件箱”对应的公开行为。
- THEN 通知正确渲染并跳转到目标对象，曝光/点击/已读事件使用同一通知身份，未读徽标随已读事实递减。
- AND 失败时返回 canonical failure，且不产生伪成功事实。

<a id="gwt-002"></a>
### GWT-002 Gathering invitation 重放、撤销与越权均安全收敛

- GIVEN Circle 发布一条只含 canonical IDs、Purpose 摘要、披露安全时间地点与 owner action versions 的邀请事件。
- WHEN 同一事件重放，随后邀请被撤回、过期或 Gathering 取消，并有非收件人或收件人在取消后点击 action。
- THEN 收件箱始终只有一张邀请卡，终态/过期后不再返回可执行 intent，未加入期间无群内容或私密地点泄露。
- AND 非收件人与取消后点击由 Circle canonical error 拒绝；接受成功后 room access 只由既有 membership projection 授予。

## 6. 依赖

- 前置要求：[`commercial-message-system`](../spec.md) 的范围、要求与 SIT。
- 下游结果：本 Story 声明的 GWT 可观察结果。
- 父级设计：[L1 DEC-001](../../design.md#dec-001)

## 7. 开放事项

<a id="open-001"></a>
### OPEN-001 Push 外送商用闭环

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：仍缺 APNs/FCM 非内存 Provider 投递与终态回执、失败重试/DLQ 运行证据、同一候选四环境 readback 及 Android/iPhone 真机验收。`NotificationDeliveryJob` 对象、Mongo store/outbox、受保护路由的 production composition 与真实 Mongo `api_integration` 已存在。外部投递无法确认时必须 fail-closed，不影响已落盘站内通知可读。
- 完成判定：`GWT-001` 对应的站内与 push 行为均满足，且真实 `api_integration`、`user_acceptance` CaseResult 直接引用本节点。

<a id="open-002"></a>
### OPEN-002 Gathering invitation AppMessage 尚缺 App 动作与 Remote UAT

- 类型：`capability_gap`
- 优先级：`P0`
- 准出影响：`block`
- 尚缺实现：未批准 App ContractGraph handoff 下的 Circle accept/decline generated client、消息页邀请卡操作按钮，以及真实账号 production Remote user_acceptance。
- 影响或价值：尚缺 App handoff 后的 generated accept/decline、邀请卡操作与 Remote UAT；服务端 transactional outbox、Notification 幂等折叠/终态刷新、仅收件人授权和接受后 membership projection 已由 local_contract/api_integration 证明，完成前邀请卡只能结构化不可用，不得伪造接受、拒绝或入群成功。
- 完成判定：App 使用 generated client 展示并执行 accept/decline；同一 invitation 重放只保留一张卡，乱序旧事件不能复活 action，非收件人与终态点击均返回 Circle canonical failure，after_join 精确地点和群内容泄露为零，并由 user_acceptance CaseResult 直接引用 `GWT-002`。
- 依赖：批准后的 App ContractGraph handoff、Circle accept/decline generated client 与真实账号 Remote UAT。
