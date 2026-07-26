# L3 Story：member-add-remove-policy — 群成员增减与解散边界 (`member-add-remove-policy`)

> 所属能力：[`group-creation-member-management`](../spec.md)

> Journey / Scenario：[`JNY-007 / SCN-013`](../../../spec.md#scn-013)

> 设计归属：[L2 DEC-001](../design.md#dec-001)

## 1. 用户价值

作为发起或接收消息的用户，
我希望圈子绑定默认群（`group + circleId`）：跟随圈子绑定关系，不能单独进入 `dissolved`，
从而稳定完成会话、消息或通话协作。

## 2. 范围与非目标

### In Scope

- “member-add-remove-policy — 群成员增减与解散边界”的输入、可观察主路径、失败语义以及与父能力的交接。
- AddMembers 操作者须为活跃成员。
- 新成员互关/拉黑 gate（圈子绑定群跳过）
- 上限 group_full。
- RemoveMember 仅 owner/admin。
- owner 不可被移出。

### Out of Scope

- 父能力中由其他 Story 独立拥有的行为、能力级架构决定和实现任务。

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 member-add-remove-policy — 群成员增减与解散边界

- 圈子绑定默认群（`group + circleId`）：跟随圈子绑定关系，不能单独进入 `dissolved`。

<a id="req-002"></a>
### REQ-002 圈子绑定默认群（group + circleId）：跟随圈子绑定关系，不能单独进入 dissolved

- 圈子绑定默认群（`group + circleId`）：跟随圈子绑定关系，不能单独进入 `dissolved`
- 端侧候选页不得展示“不可加入但可点选”的成员。
- 不接受对来源与成员资格的模糊容忍，成员添加必须严格执行互关准入。
- 加人失败不得清空当前已选成员。
- 危险操作入口隐藏与服务端拒绝必须同时存在，避免单端绕过。

<a id="req-003"></a>
### REQ-003 必须群成员进出治理策略：加人授权与关系 gate、移出角色矩阵、自愿退群语义、离群收件箱清理与解散终态，且失败时不得写入成功事实

- 系统必须群成员进出治理策略：加人授权与关系 gate、移出角色矩阵、自愿退群语义、离群收件箱清理与解散终态，且失败时不得写入成功事实。

<a id="req-004"></a>
### REQ-004 服务本地契约引用边界

- 跨边界字段、operation 与错误语义只引用所属服务 contracts；本节点不得复制 wire 定义。

## 4. 契约引用

- canonical：`quwoquan_service/services/chat-service/contracts/chat/conversation_membership/operations.yaml#AddMembers`
- canonical：`quwoquan_service/services/chat-service/contracts/chat/conversation_membership/operations.yaml#RemoveMember`
- canonical：`quwoquan_service/services/chat-service/contracts/chat/conversation_membership/operations.yaml#LeaveConversation`
- canonical：`quwoquan_service/services/chat-service/contracts/chat/conversation/errors.yaml`

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 member-add-remove-policy — 群成员增减与解散边界

- GIVEN 发起或接收消息的用户具备有效身份，且父能力声明的输入与上游事实成立。
- WHEN 参与者执行“member-add-remove-policy — 群成员增减与解散边界”对应的公开行为。
- THEN 圈子绑定默认群（`group + circleId`）：跟随圈子绑定关系，不能单独进入 `dissolved`。
- AND 失败时返回 canonical failure，且不产生伪成功事实。

## 6. 依赖

- 前置要求：[`group-creation-member-management`](../spec.md) 的范围、要求与 SIT。
- 下游结果：本 Story 声明的 GWT 可观察结果。
- 父级设计：[L2 DEC-001](../design.md#dec-001)
