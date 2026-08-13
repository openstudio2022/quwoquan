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
- canonical：`quwoquan_service/services/circle-service/contracts/circle_management/circle_group_membership/operations.yaml`
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
- THEN role_changed 只更新既有 Chat member，不创建重复名册行；Chat HTTP 成员治理全部返回 chat conversation errors 的 `source_managed_conversation`（source-managed 会话把成员治理权交还来源对象）。

以下 operation 级 GWT 只裁定 CircleGroupMembership owner 的 command/query 终态；它们不替代 GWT-001/GWT-002 对 Chat binding、Inbox、realtime、重复/乱序、reclaim、DLQ 与 health 的跨服务终态要求。

<a id="gwt-003"></a>
### GWT-003 申请加入 CircleGroup

- GIVEN 调用 Persona 是 active Circle member，目标 CircleGroup 可加入且未超过 active member 容量。
- WHEN Persona 使用稳定幂等键提交 canonical `ApplyJoinCircleGroup`。
- THEN command receipt 与 owner authoritative readback 收敛到同一 membership、version 及符合 join policy 的 state，且只提交一次状态变化与 outbox。
- THEN 相同幂等键重放同一语义命令返回同一 membership 与 receipt 身份，不增加 version、membership 或 outbox。
- THEN 容量、资格、归档或幂等冲突返回 canonical typed failure，owner state、receipt 与 outbox 不产生部分成功。

<a id="gwt-004"></a>
### GWT-004 分页读取 CircleGroup 成员关系

- GIVEN 调用 Persona 有权读取目标 CircleGroup 的成员关系，且至少存在一条匹配筛选条件的 membership。
- WHEN Persona 提交 canonical `ListCircleGroupMemberships` 并沿 owner cursor 继续分页。
- THEN 每页返回 nonempty typed `CircleGroupMembershipPageSlice`，只披露公开 membership slice，不暴露 storage identity 或 decision actor。
- THEN cursor 分页保持稳定顺序且不重复、不漏项，筛选 state 与下一页 cursor 均由 owner reader 裁定。
- THEN 无权枚举、非法 cursor 或 owner reader 失败返回 canonical typed failure，不泄露任何成员数据，也不合成成功空页。

<a id="gwt-005"></a>
### GWT-005 读取本人 CircleGroup 成员关系

- GIVEN 调用 Persona 在目标 CircleGroup 中存在可读取的本人 membership。
- WHEN Persona 提交 canonical `GetMyCircleGroupMembership`。
- THEN 返回 nonempty typed `CircleGroupMembershipSlice`，其 persona、group、circle、state、role 与 owner authoritative readback 一致。
- THEN 查询主体固定为认证 Persona，调用方不能通过 path、query 或 payload 探测其他 Persona 的 membership。
- THEN membership 不存在、身份不匹配或 owner reader 失败返回对应 canonical typed failure，不把依赖失败合成为“未加入”成功态。

<a id="gwt-006"></a>
### GWT-006 离开 CircleGroup

- GIVEN 调用 Persona 拥有允许离开的 active CircleGroup membership。
- WHEN Persona 使用稳定幂等键提交 canonical `LeaveCircleGroup`。
- THEN command receipt 与 owner authoritative readback 收敛到同一 membership 的 left state 与新 version，且只提交一次状态变化与 outbox。
- THEN 相同幂等键重放同一语义命令返回同一 membership 与 receipt 身份，不重复推进 version 或 outbox。
- THEN owner 不可离开、version 冲突、membership 不存在或幂等冲突返回 canonical typed failure，owner state、receipt 与 outbox 不产生部分成功。

<a id="gwt-007"></a>
### GWT-007 审批 CircleGroup 加入申请

- GIVEN 调用 Persona 是目标 CircleGroup owner 或 manager，目标 membership 处于可审批状态且容量可用。
- WHEN 调用 Persona 使用稳定幂等键提交 canonical `ApproveCircleGroupMember`。
- THEN command receipt 与 owner authoritative readback 收敛到目标 membership 的 active state 与新 version，且只提交一次状态变化与 outbox。
- THEN 相同幂等键重放同一语义命令返回同一 membership 与 receipt 身份，不重复推进 version、容量占用或 outbox。
- THEN BOLA、容量、状态、version 或幂等冲突返回 canonical typed failure，owner state、receipt、容量与 outbox 不产生部分成功。

<a id="gwt-008"></a>
### GWT-008 拒绝 CircleGroup 加入申请

- GIVEN 调用 Persona 是目标 CircleGroup owner 或 manager，目标 membership 处于可拒绝状态。
- WHEN 调用 Persona 使用稳定幂等键提交 canonical `RejectCircleGroupMember`。
- THEN command receipt 与 owner authoritative readback 收敛到目标 membership 的 rejected state 与新 version，且只提交一次状态变化与 outbox。
- THEN 相同幂等键重放同一语义命令返回同一 membership 与 receipt 身份，不重复推进 version 或 outbox。
- THEN BOLA、状态、version 或幂等冲突返回 canonical typed failure，owner state、receipt 与 outbox 不产生部分成功。

<a id="gwt-009"></a>
### GWT-009 移除 CircleGroup 成员

- GIVEN 调用 Persona 是目标 CircleGroup owner 或 manager，目标 membership 可被移除且不是受保护 owner。
- WHEN 调用 Persona 使用稳定幂等键提交 canonical `RemoveCircleGroupMember`。
- THEN command receipt 与 owner authoritative readback 收敛到目标 membership 的 removed state 与新 version，且只提交一次状态变化与 outbox。
- THEN 相同幂等键重放同一语义命令返回同一 membership 与 receipt 身份，不重复推进 version 或 outbox。
- THEN BOLA、owner 保护、version、状态或幂等冲突返回 canonical typed failure，owner state、receipt 与 outbox 不产生部分成功。

<a id="gwt-010"></a>
### GWT-010 更新 CircleGroup 成员角色

- GIVEN 调用 Persona 是目标 CircleGroup owner，目标 membership 存在且目标角色合法。
- WHEN 调用 Persona 使用稳定幂等键提交 canonical `UpdateCircleGroupMemberRole`。
- THEN command receipt 与 owner authoritative readback 收敛到目标 membership 的新 role 与 version，且只提交一次状态变化与 outbox。
- THEN 相同幂等键重放同一语义命令返回同一 membership 与 receipt 身份，不重复推进 version 或 outbox。
- THEN BOLA、非法角色、version、状态或幂等冲突返回 canonical typed failure，owner state、receipt 与 outbox 不产生部分成功。

以下 CircleGroup aggregate operation 级 GWT 只裁定 owner command/query 终态；它们不替代 GWT-001/GWT-002 对 Chat durable binding、Conversation/成员与 Inbox 可达性、realtime 清理、重复/乱序、reclaim、DLQ 与 health 的跨服务终态要求。

<a id="gwt-011"></a>
### GWT-011 创建 CircleGroup

- GIVEN 调用 Persona 是 active Circle member，且创建权限、父层级、群组类型、可见性与加入策略均有效。
- WHEN Persona 使用稳定幂等键提交 canonical `CreateCircleGroup`。
- THEN command receipt 与 fresh `GetCircleGroup` authoritative readback 收敛到同一 active group identity、初始 version 与创建策略，且只提交一次 CircleGroup 状态变化与 `CircleGroupCreated` outbox。
- THEN 相同幂等键重放同一语义命令返回同一 group 与 receipt 身份，不创建第二个 group，不重复推进 version 或 outbox。
- THEN BOLA、父层级、默认公共群唯一性、存储或幂等冲突返回 canonical typed failure，CircleGroup state、receipt 与 outbox 不产生部分成功。

<a id="gwt-012"></a>
### GWT-012 归档 CircleGroup

- GIVEN 调用 Persona 是目标 CircleGroup owner，目标不是受保护的默认公共群且仍处于可归档状态。
- WHEN Persona 使用稳定幂等键提交 canonical `ArchiveCircleGroup`。
- THEN command receipt 与 fresh `GetCircleGroup` authoritative readback 收敛到同一 group identity、archived state 与新 version，且只提交一次状态变化与 `CircleGroupArchived` outbox。
- THEN 相同幂等键重放同一语义命令返回同一 group 与 receipt 身份，不重复推进 version 或 outbox。
- THEN BOLA、默认公共群保护、group 不存在、version 或幂等冲突返回 canonical typed failure，CircleGroup state、receipt 与 outbox 不产生部分成功。

## 6. 依赖

- 前置要求：[`circle-collaboration-tools`](../spec.md) 的范围、要求与 SIT。
- 下游结果：本 Story 声明的 GWT 可观察结果。
- 父级设计：[L2 DEC-001](../design.md#dec-001)

## 7. 开放事项

（当前无开放事项：GWT-001..GWT-012 均已由真实测试子句级绑定。）
