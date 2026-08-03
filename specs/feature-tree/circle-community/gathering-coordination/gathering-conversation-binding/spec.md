# L3 Story：Gathering 会话绑定 (`gathering-conversation-binding`)

> 所属能力：[`gathering-coordination`](../spec.md)

> Journey / Scenario：[`JNY-011 / SCN-027`](../../../spec.md#scn-027)

> 设计归属：[L2 DEC-002](../design.md#dec-002)

## 1. 用户价值

作为已经加入一次相聚的用户，
我希望马上进入一个只有同行者在的群里商量具体安排，并能直接开语音把事情说清楚，
从而不必再另外拉群或交换联系方式。

## 2. 范围与非目标

### In Scope

- Gathering 与其群会话的绑定关系。
- 加入后进入绑定会话的路径与成员同步。
- 绑定会话内发起群通话的入口复用。

### Out of Scope

- 消息投递、已读与通话信令，由 `chat-conversation` 负责。
- 参与者审批与容量，由 [`gathering-participant-roster`](../gathering-participant-roster/spec.md) 负责。

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 Gathering 只持有会话引用

- Gathering 只持有其群会话引用，不拥有消息、成员资格或通话事实。

<a id="req-002"></a>
### REQ-002 加入后可进入绑定会话

- 状态为已加入的参与者必须能从 Gathering 进入其绑定群会话；未加入者不得进入。

<a id="req-003"></a>
### REQ-003 名单与会话成员保持一致

- 参与者退出后必须同步退出绑定会话；名单与会话成员不得长期不一致。

<a id="req-004"></a>
### REQ-004 语音复用绑定会话内既有群通话

- 绑定会话内的群通话入口必须复用消息域既有能力；不得新建语音房对象，也不得新增独立行动键。

<a id="req-005"></a>
### REQ-005 绑定失败不得伪造已加入

- 绑定会话创建失败时不得标记为已加入；重试不得产生重复会话。

<a id="req-006"></a>
### REQ-006 服务本地契约引用边界

- 跨边界字段、operation 与错误语义只引用所属服务 contracts；本节点不得复制 wire 定义。

## 4. 契约引用

- canonical：`quwoquan_service/services/chat-service/contracts/chat/conversation/fields.yaml`
- canonical：`quwoquan_service/services/chat-service/contracts/chat/conversation/operations.yaml`
- canonical：`quwoquan_service/services/circle-service/contracts/circle_management/gathering/fields.yaml`
- canonical：`quwoquan_service/services/circle-service/contracts/circle_management/gathering/events.yaml`
- 父能力公开契约：[`L2 spec`](../spec.md)

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 加入后进入绑定会话并可发起群通话

- GIVEN 一个已绑定群会话的 Gathering。
- WHEN 一位账号加入后进入该绑定会话并发起群通话。
- THEN 该账号可在会话内收发消息并进入通话。
- AND 全程不产生独立的语音房对象。

<a id="gwt-002"></a>
### GWT-002 绑定失败不伪造已加入

- GIVEN 绑定会话创建失败。
- WHEN 账号尝试加入该 Gathering。
- THEN 返回 canonical failure 且该账号不被标记为已加入。
- AND 重试成功后不产生重复会话。

## 6. 依赖

- 前置要求：[`gathering-coordination`](../spec.md) 的范围、要求与 SIT。
- 下游结果：本 Story 声明的 GWT 可观察结果。
- 父级设计：[L2 DEC-002](../design.md#dec-002)

## 7. 开放事项

<a id="open-001"></a>
### OPEN-001 App 会话承接与完整实时旅程尚未验收

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`block`
- 影响或价值：尚缺 App 从 Gathering 进入绑定会话并发起群通话的完整旅程及同一候选验收；Circle→Chat 受信任 typed port、Chat 唯一会话/成员投影、事务 outbox、反向事件、durable checkpoint/retry 与真实 Mongo rollback/replay 证据已经落地。
- 完成判定：`GWT-001` 与 `GWT-002` 对应行为满足且真实测试 `spec_ref` 有效
