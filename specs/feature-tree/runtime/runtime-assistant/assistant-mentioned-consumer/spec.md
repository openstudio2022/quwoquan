# L3 Story：助手被提及消费者 (`assistant-mentioned-consumer`)

> 所属能力：[`runtime-assistant`](../spec.md)
>
> Journey / Scenario：[`JNY-009 / SCN-018`](../../../spec.md#scn-018)
>
> 设计归属：[L1 DEC-001](../../design.md#dec-001)

## 1. 用户价值

作为开发、测试或运维角色，我希望消费 chat 域可靠事件流 `events.chat.assistant_mentions`：群聊 @小趣 后拉取会话窗口消息做话题理解，代小趣成员回帖，从而让调用方获得稳定结果，并让维护者能够定位和恢复失败。

## 2. 范围与非目标

### In Scope

- AssistantMentioned Redis Stream 消费与 DLQ
- 会话窗口拉取、成员校验、代发回复

### Out of Scope

- chat 会话成员治理（归 chat-conversation）

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 群聊 @小趣 消费与回复

- 处理失败进入 DLQ 可重放；小趣被移除成员后 ack-and-drop。

<a id="req-002"></a>
### REQ-002 必须走 Redis Stream consumer group（含 DLQ `events.chat.assistant_mentions.dlq`），不得只依赖 realtime Pub/Sub

- 必须走 Redis Stream consumer group（含 DLQ `events.chat.assistant_mentions.dlq`），不得只依赖 realtime Pub/Sub。
- 回帖前必须校验小趣仍是会话成员；成员被移除后事件按 ack-and-drop 处理。

## 4. 契约引用

- canonical：`quwoquan_service/services/assistant-service/contracts/assistant/assistant_run/operations.yaml`

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 群聊 @小趣 消费与回复

- GIVEN 小趣是群会话成员，chat 域发布 AssistantMentioned 事件。
- WHEN assistant-service consumer 领取事件。
- THEN 拉取消息窗口生成回复并经 SendMessage 发回会话。
- THEN 重复事件只处理一次；处理失败写入保留原事件坐标的脱敏 DLQ 后 ACK，修复后可重放。
- THEN 回帖前从 chat 公开成员接口确认对应小趣成员与技能身份仍有效；已移除或身份已变更时直接 ACK 且不读取消息窗口、不生成 Run、不回帖。

## 6. 依赖

- 前置要求：[`runtime-assistant`](../spec.md) 的范围、要求与 SIT。
- 下游结果：本 Story 声明的 GWT 可观察结果。
- 父级设计：[L1 DEC-001](../../design.md#dec-001)

## 7. 开放事项

<a id="open-001"></a>
### OPEN-001 被引用对象的授权事实 grounding 与环境证明

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`block`
- 影响或价值：尚缺 assistant-service 按当前成员权限回查被引用对象 tagRefs、交集事实和可见性的 grounding，以及真实环境回答与引用 readback；durable consumer、幂等、DLQ、成员复核与经 Chat HTTP 回帖已有集成证据，当前会话窗口可提取消息卡 canonical objectRef。
- 完成判定：`GWT-001` 的成员与身份校验、消息窗口回复对应行为满足——被引用对象只经所属领域公开 Reader grounding，权限失败不注入；API integration 覆盖 objectRef→facts→prompt→reply，alpha/beta/gamma 取得真实身份、真实对象与回复引用证据
