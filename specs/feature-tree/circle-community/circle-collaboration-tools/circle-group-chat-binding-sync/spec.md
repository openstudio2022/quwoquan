# L3 Story：圈子群聊会话绑定同步 (`circle-group-chat-binding-sync`)

> 所属能力：[`circle-collaboration-tools`](../spec.md)
>
> Journey / Scenario：[`JNY-007 / SCN-013`](../../../spec.md#scn-013)
>
> 设计归属：[L2 DEC-001](../design.md#dec-001)

## 1. 用户价值

作为圈子成员或圈子运营者，我希望CircleGroup 是群单元、成员与角色的权威对象；Conversation 只提供消息能力。用户加入、离开、，从而完成可治理的社区协作。

## 2. 范围与非目标

### In Scope

- CircleGroup 创建、成员 active/left/removed/role_changed、归档的 durable Stream 投影和双向绑定
- 圈群容量、Chat HTTP 旁路拒绝、终态 Inbox/realtime 清理、DLQ/health/metrics

### Out of Scope

- 文件、资料、公开内容、二维码邀请与跨圈迁移

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 CircleGroup 创建后可靠建立唯一聊天绑定

- Circle HTTP create -> Redis Stream -> Chat Mongo -> reverse Stream -> Circle Mongo 的真实 API integration 通过。
- 消费者必须校验 payload，按事件身份幂等处理乱序与 reclaim；不可处理事件进入 DLQ。

<a id="req-002"></a>
### REQ-002 CircleGroup 成员生命周期准确收敛到聊天名册与 Inbox

- Redis + Mongo 双服务 API integration 覆盖完整状态机、重复/乱序、realtime 与 Inbox readback。
- 成员加入后可见群会话；离开或被移除后 Inbox 与本地缓存清除该会话，管理入口回到圈子 owner。

<a id="req-003"></a>
### REQ-003 CircleGroup 与 Chat 统一限制为 1000 active human members

- CircleGroup 与 Chat 统一限制为 1000 active human members；容量满必须在 Circle membership

## 4. 契约引用

- canonical：`quwoquan_service/services/circle-service/contracts/circle_management/circle_group/events.yaml#CircleGroupCreated`
- canonical：`quwoquan_service/services/chat-service/contracts/chat/conversation/events.yaml#CircleGroupConversationProvisioned`
- canonical：`quwoquan_service/services/circle-service/contracts/circle_management/circle_group_membership/events.yaml`
- canonical：`quwoquan_service/services/chat-service/contracts/chat/conversation_membership/object.yaml`

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 CircleGroup 创建后可靠建立唯一聊天绑定

- GIVEN active CircleGroup 已经由 circle-service 真实命令创建，CircleGroupCreated 在 Redis Stream 可重放。
- WHEN chat circle-group provisioner 消费创建事实，随后 circle binding projector 消费回写事实。
- THEN Conversation、owner ConversationMember、owner ConversationUserState 与 Chat outbox 在同一事务提交。
- THEN Conversation.circleGroupId 与 CircleGroup.conversationId 双向一对一；重复或 reclaim 事件不创建第二个对象。
- THEN chat 持久化或回写失败时 source message 不 ACK，达到重试上限进入带 TTL DLQ 且 health/metric 可见。

<a id="gwt-002"></a>
### GWT-002 CircleGroup 成员生命周期准确收敛到聊天名册与 Inbox

- GIVEN 已绑定 CircleGroup 与 Conversation 存在，成员申请、审批、离开、移除和角色变更通过 CircleGroupMembership 命令产生 outbox。
- WHEN chat membership projector 消费对应 Stream 事件并发生重复、乱序或重启 reclaim。
- THEN active 只创建一次 Chat member/UserState，role 映射为 owner/admin/member。
- THEN left/removed 原子删除 UserState 和 ChatInbox 可达性，迟到 MessageSent 不得复活。
- THEN role_changed 只更新既有 Chat member，不创建重复名册行；Chat HTTP 成员治理全部返回 circle_group_managed_by_circle。

## 6. 依赖

- 前置要求：[`circle-collaboration-tools`](../spec.md) 的范围、要求与 SIT。
- 下游结果：本 Story 声明的 GWT 可观察结果。
- 父级设计：[L2 DEC-001](../design.md#dec-001)

## 7. 开放事项

<a id="open-001"></a>
### OPEN-001 CircleGroup 创建后可靠建立唯一聊天绑定

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`；目标：Circle HTTP create -> Redis Stream -> Chat Mongo -> reverse Stream -> Circle Mongo 的真实 API integration 通过。
- 完成判定：`GWT-001` 对应行为满足且真实测试 `spec_ref` 有效

<a id="open-002"></a>
### OPEN-002 CircleGroup 成员生命周期准确收敛到聊天名册与 Inbox

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`；目标：Redis + Mongo 双服务 API integration 覆盖完整状态机、重复/乱序、realtime 与 Inbox readback。
- 完成判定：`GWT-002` 对应行为满足且真实测试 `spec_ref` 有效
