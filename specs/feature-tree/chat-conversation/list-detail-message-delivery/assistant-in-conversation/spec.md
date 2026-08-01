# L3 Story：助手圈内会话 (`assistant-in-conversation`)

> 所属能力：[`list-detail-message-delivery`](../spec.md)
>
> Journey / Scenario：[`JNY-007 / SCN-012`](../../../spec.md#scn-012)
>
> 设计归属：[L1 DEC-001](../../design.md#dec-001)

## 1. 用户价值

作为发起或接收消息的用户，我希望小趣以 `ConversationMember.memberType=assistant` 参与 direct/group 会话：可被邀入、被移除，@小趣 触发 AssistantMentioned 可靠事件，从而稳定完成会话、消息或通话协作。

## 2. 范围与非目标

### In Scope

- assistant memberType 成员生命周期
- mention 事实与 AssistantMentioned 事件发布

### Out of Scope

- 小趣回复生成（归 runtime-assistant/assistant-mentioned-consumer）

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 会话内 @小趣 事件链

- 小趣被移除后新 mention 不再发布事件；AssistantRemoved 生效。

<a id="req-002"></a>
### REQ-002 个人助手全屏会话（AssistantSession）与会话内 @小趣 共享助手 runtime，不得把个人助手会话伪装成 chat Conversation

- 个人助手全屏会话（AssistantSession）与会话内 @小趣 共享助手 runtime，不得把个人助手会话伪装成 chat Conversation。

## 4. 契约引用

- canonical：`quwoquan_service/services/chat-service/contracts/chat/conversation/operations.yaml`

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 会话内 @小趣 事件链

- GIVEN 会话中含 memberType=assistant 的小趣成员。
- WHEN 用户发送 @小趣 消息。
- THEN chat 域持久化 mention 事实并发布 AssistantMentioned 到可靠事件流。

## 6. 依赖

- 前置要求：[`list-detail-message-delivery`](../spec.md) 的范围、要求与 SIT。
- 下游结果：本 Story 声明的 GWT 可观察结果。
- 父级设计：[L1 DEC-001](../../design.md#dec-001)

## 7. 开放事项

- 无。
