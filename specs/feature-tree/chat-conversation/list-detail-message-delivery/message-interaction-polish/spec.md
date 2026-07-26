# L3 Story：消息交互体验增强（Message Interaction Polish） (`message-interaction-polish`)

> 所属能力：[`list-detail-message-delivery`](../spec.md)

> Journey / Scenario：[`JNY-007 / SCN-012`](../../../spec.md#scn-012)

> 设计归属：[L1 DEC-001](../../design.md#dec-001)

## 1. 用户价值

作为发起或接收消息的用户，
我希望ChatPage 混用 `ChatRepository` 和 `appContentRepository`，数据源不统一导致列表内容不一致，
从而稳定完成会话、消息或通话协作。

## 2. 范围与非目标

### In Scope

- “消息交互体验增强（Message Interaction Polish）”的输入、可观察主路径、失败语义以及与父能力的交接。
- 输入 @ 打开成员选择器。
- 服务端搜索最多返回 50 个结果。
- 选择后插入 @显示名 与稳定 userId。
- 普通成员提及、owner/admin @所有人、assistant 已入群时 @小趣的服务端校验。
- Message/MessageSent/ListMessages/SyncMessages mentions 同源与 mentionUnreadCount 推进、已读归零。

### Out of Scope

- 父能力中由其他 Story 独立拥有的行为、能力级架构决定和实现任务。

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 消息交互体验增强（Message Interaction Polish）

- **会话列表数据源**：ChatPage 混用 `ChatRepository` 和 `appContentRepository`，数据源不统一导致列表内容不一致。

<a id="req-002"></a>
### REQ-002 会话列表数据源：ChatPage 混用 ChatRepository 和 appContentRepository，数据源不统一导致列表内容不一致

- **会话列表数据源**：ChatPage 混用 `ChatRepository` 和 `appContentRepository`，数据源不统一导致列表内容不一致。
- 引用回复 UI 使用 `AppTypography`/`AppSpacing`/`AppColors`，禁止硬编码视觉字面量。
- @提及高亮使用 `TextSpan` 富文本渲染，禁止正则替换 HTML。
- InboxService HTTP 必须通过 `runtime/http` 标准路由注册。
- `ChatPage` 数据源必须统一为 `chatRepositoryProvider`，禁止直接调用 `appContentRepository`

<a id="req-003"></a>
### REQ-003 输入选择与发送 payload

- 输入、选择、删除与发送必须产生同一强类型 payload，Mock 与 Remote 不得使用不同参数语义。

<a id="req-004"></a>
### REQ-004 服务端目标校验与提及未读

- HTTP command、Mongo Message、outbox 与 ConversationUserState 必须原子收敛，重放返回原结果。

<a id="req-005"></a>
### REQ-005 气泡高亮与主页跳转

- 自己与他人的提及气泡在深浅模式下保持可读；点击合法目标进入对应主页，双账号提醒使用同一消息事实。

<a id="req-006"></a>
### REQ-006 非法目标与越权请求失败语义

- 非成员目标、越权 `__all__`、超限或格式非法必须返回 chat-service contracts 声明的 canonical error。
- 单次候选结果 `<= 50`；服务端搜索使用转义后的字面量匹配，禁止正则注入。

## 4. 契约引用

- canonical：`quwoquan_service/services/chat-service/contracts/chat/conversation_membership/operations.yaml#ListMembers`
- canonical：`quwoquan_service/services/chat-service/contracts/chat/message/operations.yaml#SendMessage`
- canonical：`quwoquan_service/services/chat-service/contracts/chat/message/fields.yaml#mentions`
- canonical：`quwoquan_service/services/chat-service/contracts/chat/message/events.yaml#MessageSent`
- canonical：`quwoquan_service/services/chat-service/contracts/chat/conversation_user_state/fields.yaml#mentionUnreadCount`
- canonical：`quwoquan_service/services/chat-service/contracts/chat/conversation/projections/chat_message_client.yaml`
- canonical：`quwoquan_service/contracts/metadata/_shared/app_routes.yaml#userProfile`

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 消息交互体验增强（Message Interaction Polish）

- GIVEN 发起或接收消息的用户具备有效身份，且父能力声明的输入与上游事实成立。
- WHEN 参与者执行“消息交互体验增强（Message Interaction Polish）”对应的公开行为。
- THEN **会话列表数据源**：ChatPage 混用 `ChatRepository` 和 `appContentRepository`，数据源不统一导致列表内容不一致。
- AND 失败时返回 canonical failure，且不产生伪成功事实。

<a id="gwt-003"></a>
### GWT-003 输入选择与发送 payload

- GIVEN 用户在会话中输入内容并选择提及目标。
- WHEN 用户删除、保留或发送已编辑的输入。
- THEN Mock 与 Remote 使用同一强类型 payload，并保留一致的提及语义。

<a id="gwt-004"></a>
### GWT-004 服务端目标校验与提及未读

- GIVEN 消息命令包含合法或非法的提及目标。
- WHEN 服务端处理首次或重放的发送请求。
- THEN Message、outbox 与 ConversationUserState 原子收敛，非法目标按 canonical error 拒绝。

<a id="gwt-005"></a>
### GWT-005 气泡高亮与主页跳转

- GIVEN 会话中存在自己或他人的合法提及消息。
- WHEN 用户查看提及气泡并点击目标。
- THEN 深浅模式下高亮可读，且导航至对应主页或提供可恢复降级。

## 6. 依赖

- 前置要求：[`list-detail-message-delivery`](../spec.md) 的范围、要求与 SIT。
- 下游结果：本 Story 声明的 GWT 可观察结果。
- 父级设计：[L1 DEC-001](../../design.md#dec-001)

## 7. 开放事项

<a id="open-001"></a>
### OPEN-001 消息交互体验增强（Message Interaction Polish） 验收证据

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺少能够证明“消息交互体验增强（Message Interaction Polish）”已满足当前规格的真实测试证据。
- 完成判定：`GWT-001` 对应行为满足且真实测试 `spec_ref` 有效。

<a id="open-002"></a>
<a id="open-003"></a>
### OPEN-003 输入选择与发送 payload

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`。
- 目标：输入、选择、删除与发送行为有 local_contract，Mock 与 Remote 参数一致。
- 完成判定：`GWT-003` 对应行为满足且真实测试 `spec_ref` 有效。

<a id="open-004"></a>
### OPEN-004 服务端目标校验与提及未读

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`。
- 目标：HTTP、Mongo Message、outbox 与 ConversationUserState 由 api_integration 证明一致且重放幂等。
- 完成判定：`GWT-004` 对应行为满足且真实测试 `spec_ref` 有效。

<a id="open-005"></a>
### OPEN-005 气泡高亮与主页跳转

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`。
- 目标：气泡 local_contract 覆盖自己/他人消息、深浅模式和点击目标；双账号 UAT 覆盖提醒到主页旅程。
- 完成判定：`GWT-005` 对应行为满足且真实测试 `spec_ref` 有效。
