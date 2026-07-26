# L2 Business Capability：圈子协作工具 (`circle-collaboration-tools`)

> 所属领域：[`circle-community`](../spec.md)
>
> 设计归属：[本层 design.md](./design.md)

## 1. 能力目标

以圈子或组织主页内的群为协作单元，统一交流、资料与公告

## 2. 范围与非目标

### In Scope

- CircleGroup 到 Chat Conversation 的 durable 绑定、成员投影、容量、终态清理和治理边界

### Out of Scope

- 把 Conversation 重新作为 CircleGroup 的写模型或保留 Circle.conversationId 兼容路径

## 3. Journey / Scenario 贡献

- [`JNY-007 / SCN-013`](../../spec.md#scn-013)
  - 本能力处理：组合本目录 Story 的可观察行为。
  - 本能力输出：以圈子或组织主页内的群为协作单元，统一交流、资料与公告，并将可观察结果交给下游。
  - 失败时终态：可解释、可恢复且不伪造成功。
- [`JNY-008 / SCN-014`](../../spec.md#scn-014)
  - 本能力处理：组合本目录 Story 的可观察行为。
  - 本能力输出：以圈子或组织主页内的群为协作单元，统一交流、资料与公告，并将可观察结果交给下游。
  - 失败时终态：可解释、可恢复且不伪造成功。
- [`JNY-011 / SCN-027`](../../spec.md#scn-027)
  - 本能力处理：组合本目录 Story 的可观察行为。
  - 本能力输出：以圈子或组织主页内的群为协作单元，统一交流、资料与公告，并将可观察结果交给下游。
  - 失败时终态：可解释、可恢复且不伪造成功。

## 4. Story



- [`circle-group-chat-binding-sync`](./circle-group-chat-binding-sync/spec.md)：Circle HTTP create -> Redis Stream -> Chat Mongo -> reverse Stream -> Circle Mongo 的真实 API integration 通过。

## 5. 能力要求

<a id="req-001"></a>
### REQ-001 circle collaboration tools 能力 SIT

- CircleGroup 创建、成员状态机、Chat 名册/Inbox、反向绑定、DLQ/health 与客户端终态体验可端到端验证。

<a id="req-002"></a>
### REQ-002 公共群、自建群、组织节点还没有统一的协作能力边界

- 公共群、自建群、组织节点还没有统一的协作能力边界。
- 单个 CircleGroup 的 active 成员上限与其绑定 Chat Conversation 统一为 **1000**；大型群组通过多个命名公共群或组织节点分流，禁止以异步投影静默丢失第 1001 名成员。
- CircleGroup 是成员、角色与归档生命周期的唯一写入者。它的 transactional outbox 依次驱动 Chat 名册投影，Chat 反向以 durable binding event 回写 `CircleGroup.conversationId`；不得由页面、同步 RPC 或 Chat HTTP 命令直接拼装/篡改绑定。
- `CircleGroupMembership.active / left / removed / role_changed` 必须分别同步为 Chat 的成员加入、离群清理、角色更新；`CircleGroupArchived` 必须终止绑定会话并清理所有 ChatInbox 可达性。
- 发布入口统一为 `发布内容`，从群组层入口发起；需要时可带默认 groupId 或 nodeId 作为上下文，但不改变公开内容的归属层级。
- 复用 content 域的统一内容模型，不新建群内容实体。
- 资料能力仍由 `quwoquan_service/services/circle-service/contracts/circle_management/circle_file/` 下的 typed contract 驱动；列表、单项读取和命令回执分别使用 `CircleFilePageSlice`、`CircleFileSlice` 和 `CircleFileCommandResult`，禁止以聚合存储模型或单项切片替代分页响应。
- 群交流同步必须通过事件驱动而非同步 RPC。
- 事件链必须是可重放的 Redis Stream + consumer group：`CircleGroupCreated/Archived` 和 `CircleGroupMembership*` 由 circle-service outbox relay 投递
- chat-service 成功持久化后才 ACK
- Chat 的 `CircleGroupConversationProvisioned` 由独立 durable relay 回写 circle-service。失败不得 ACK，达到受控重试上限必须写入有 TTL 的 DLQ 并触发健康检查/告警。
- Chat 的普通 `AddMembers / RemoveMember / LeaveConversation / TransferOwnership / UpdateMemberRole / DissolveConversation` 不得成为圈群成员或角色的写入口；圈群场景统一返回 metadata 定义的“由圈群管理”结构化错误。Chat 可以保留消息级设置，但不得反向改变 CircleGroup 权威成员集合。

## 6. 契约与依赖

- 上游能力：[`circle-community`](../spec.md) 声明的领域入口。
- 下游能力：本目录直接 Story 及其公开结果。
- 一致性要求：遵循本层或父 L1 DEC 声明的一致性边界。

## 7. 集成验收

<a id="sit-001"></a>
### SIT-001 circle collaboration tools 能力 SIT

- GIVEN 执行“circle collaboration tools 能力”所需的身份、输入与上游事实均有效。
- WHEN 参与者发起“circle collaboration tools 能力”对应动作。
- THEN CircleGroup 创建、成员状态机、Chat 名册/Inbox、反向绑定、DLQ/health 与客户端终态体验可端到端验证。

## 8. 开放事项

<a id="open-001"></a>
### OPEN-001 circle collaboration tools 能力 SIT

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`；目标：CircleGroup 创建、成员状态机、Chat 名册/Inbox、反向绑定、DLQ/health 与客户端终态体验可端到端验证。
- 完成判定：`SIT-001` 对应行为满足且真实测试 `spec_ref` 有效
