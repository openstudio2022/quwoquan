# L3 Story：group-create-flow — 全局添加入口发起群聊 (`group-create-flow`)

> 所属能力：[`group-creation-member-management`](../spec.md)

> Journey / Scenario：[`JNY-007 / SCN-013`](../../../spec.md#scn-013)

> 设计归属：[L2 DEC-001](../design.md#dec-001)

## 1. 用户价值

作为发起群聊的用户，
我希望从全局添加入口选择互相关注且未屏蔽的联系人创建群聊，并对重复、超限或无权限获得明确提示，
从而一次完成可恢复且成员边界正确的群聊创建。

## 2. 范围与非目标

### In Scope

- “group-create-flow — 全局添加入口发起群聊”的输入、可观察主路径、失败语义以及与父能力的交接。
- 三来源服务端权威读取、搜索、互关过滤、跨来源 userId 去重与已选反馈。
- CreateConversation 初始成员的互关/拉黑/去重/1000 人上限校验。
- 建群成功后聊天详情可进入且 Inbox 可权威回读。
- 圈子或圈子群创建。
- 企业联系人、群二维码和邀请链接。

### Out of Scope

- 父能力中由其他 Story 独立拥有的行为、能力级架构决定和实现任务。

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 group-create-flow — 全局添加入口发起群聊

- 全局添加入口必须只返回互关且未屏蔽的候选；重复请求不得重复建群，容量越界必须拒绝且不写 outbox。

<a id="req-002"></a>
### REQ-002 服务端原子建群与成员策略

- 服务端必须原子创建 Conversation、初始 Membership 与 outbox；任一步失败均不得留下部分群聊。

<a id="req-003"></a>
### REQ-003 建群成功进入详情并回流消息列表

- 从圈子或全局入口选成员并建群后必须进入详情，随后 Inbox 可回读同一会话。

<a id="req-004"></a>
### REQ-004 统一接收初始成员列表

- 统一接收初始成员列表。
- 服务端必须在分页前执行 `source=group|circle` 过滤，禁止端侧拿一页后再过滤。
- 深色模式不能退化为纯黑白替换，必须保留层级与轻表面。
- `memberCountBucket` 只允许登记闭集人数分桶；禁止以来源组合、`userId` 等高基数值作为标签。
- 服务黄金信号来自统一 `http_server_*` 和受控 Prometheus 指标，覆盖建群与候选源的请求量、成功率、错误率和延迟。
- Message/Conversation/Membership/UserState outbox relay 与 InboxProjector 必须注册。
- beta integration、gamma release 与 prod 只读验收统一由环境 validation suite 执行。

<a id="req-005"></a>
### REQ-005 必须从全局添加入口经互关联系人、私建群或圈子绑定群三类来源选人，原子创建私建群并进入新会话、回流 Inbox，且失败时不得写入成功事实

- 系统必须从全局添加入口经互关联系人、私建群或圈子绑定群三类来源选人，原子创建私建群并进入新会话、回流 Inbox，且失败时不得写入成功事实。

<a id="req-006"></a>
### REQ-006 服务本地契约引用边界

- 跨边界字段、operation 与错误语义只引用所属服务 contracts；本节点不得复制 wire 定义。

## 4. 契约引用

- canonical：`quwoquan_service/services/chat-service/contracts/chat/conversation/operations.yaml#ListSelectableGroupConversations`
- canonical：`quwoquan_service/services/chat-service/contracts/chat/conversation/operations.yaml#ListSelectableGroupContactMembers`
- canonical：`quwoquan_service/services/chat-service/contracts/chat/conversation/projections/selectable_group_conversation_row.yaml`
- canonical：`quwoquan_service/services/chat-service/contracts/chat/conversation/operations.yaml#CreateConversation`
- canonical：`quwoquan_service/services/chat-service/contracts/chat/conversation/errors.yaml`
- canonical：`quwoquan_service/contracts/metadata/_shared/app_routes.yaml#startGroupChat`
- canonical：`quwoquan_service/services/chat-service/contracts/chat/conversation/operations.yaml#ListInbox`
- canonical：`quwoquan_ops/observability/monitoring/alerts/quwoquan_alerts.yaml#quwoquan_l2_chat_objects`
- canonical：`quwoquan_ops/observability/monitoring/dashboards/l2_business_journey.json`
- canonical：`quwoquan_ops/environments/gamma/validation_suites.json#chat_group_lifecycle_api_probe`

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 group-create-flow — 全局添加入口发起群聊

- GIVEN 发起或接收消息的用户具备有效身份，且父能力声明的输入与上游事实成立。
- WHEN 参与者执行“group-create-flow — 全局添加入口发起群聊”对应的公开行为。
- THEN 合法成员只创建一个群聊并进入详情；非互关、屏蔽、重复或超容量请求得到稳定终态且无部分写入。
- AND 失败时返回 canonical failure，且不产生伪成功事实。

<a id="gwt-002"></a>
### GWT-002 服务端原子建群与成员策略

- GIVEN 用户从受支持来源选定初始成员。
- WHEN 服务端处理成功、非互关、屏蔽、重复或容量边界的建群请求。
- THEN Conversation、Membership 与 outbox 同时提交，或请求被稳定拒绝且不留下部分群聊。

<a id="gwt-003"></a>
### GWT-003 建群成功进入详情并回流消息列表

- GIVEN 用户从圈子或全局入口完成成员选择。
- WHEN 建群请求成功并完成会话投影。
- THEN 用户进入新会话详情，且 Inbox 可回读同一会话。

## 6. 依赖

- 前置要求：[`group-creation-member-management`](../spec.md) 的范围、要求与 SIT。
- 下游结果：本 Story 声明的 GWT 可观察结果。
- 父级设计：[L2 DEC-001](../design.md#dec-001)

## 7. 开放事项

<a id="open-001"></a>
### OPEN-001 三类来源选择与同一向导状态

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`；目标：Remote、Alpha Mock、Provider 与页面 local_contract 对 source、circleId、计数和成员交集行为一致。
- 完成判定：`GWT-001` 对应行为满足且真实测试 `spec_ref` 有效。

<a id="open-002"></a>
### OPEN-002 服务端原子建群与成员策略

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`；目标：api_integration 覆盖成功、非互关、屏蔽、重复请求、边界容量与 outbox。
- 完成判定：`GWT-002` 对应行为满足且真实测试 `spec_ref` 有效。

<a id="open-003"></a>
### OPEN-003 建群成功进入详情并回流消息列表

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`；目标：user_acceptance 覆盖“圈子来源 -> 选成员 -> 建群 -> 进入详情 -> Inbox 回读”，beta/gamma/prod smoke 均留证。
- 完成判定：`GWT-003` 对应行为满足且真实测试 `spec_ref` 有效。

<a id="open-004"></a>
### OPEN-004 group-create-flow — 全局添加入口发起群聊 验收证据

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺少能够证明“group-create-flow — 全局添加入口发起群聊”已满足当前规格的真实测试证据。
- 完成判定：`GWT-001` 对应行为满足且真实测试 `spec_ref` 有效。
