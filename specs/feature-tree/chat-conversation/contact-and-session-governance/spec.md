# L2 Business Capability：联系人与会话治理 (`contact-and-session-governance`)

> 所属领域：[`chat-conversation`](../spec.md)
>
> 设计归属：[本层 design.md](./design.md)

## 1. 能力目标

以“关注”为唯一关系概念，验证关注状态、拉黑门禁、打招呼请求箱、正式私信与 1v1 RTC 的端云一致性。

## 2. 范围与非目标

### In Scope

- RelationshipState 只保留 self/not_following/following/followed_by/mutual，mutual 不命名为额外关系等级。
- BlockEdge 作为最高优先级门禁，创建拉黑边时清除双方 FollowEdge、失效 pending GreetingRequest，并阻断关注、打招呼、建会话、发消息和 1v1 RTC。
- 非 mutual 用户只能通过 GreetingRequest 进入请求箱，回复后创建或复用正式 1v1 conversation。
- CreateConversation、SendMessage、RTC 发起必须有服务端关系门禁与结构化错误。
- 主页动作、请求箱、正式会话、blocked 会话四态与 RelationshipCapabilityView 保持一致。

### Out of Scope

- 好友、同好、密友、挚友等关系等级。
- 群对象拉黑、关系积分、亲密度、勋章。
- 群组空间、相册、文件库能力。

## 3. Journey / Scenario 贡献

- [`JNY-007 / SCN-012`](../../spec.md#scn-012)
  - 本能力处理：组合本目录 Story 的可观察行为。
  - 本能力输出：以“关注”为唯一关系概念，验证关注状态、拉黑门禁、打招呼请求箱、正式私信与 1v1 RTC 的端云一致性，并将可观察结果交给下游。
  - 失败时终态：可解释、可恢复且不伪造成功。

## 4. Story



- [`conversation-entry-matrix`](./conversation-entry-matrix/spec.md)：拉黑级联与三处服务端门禁均有真实存储/API 证据。
- [`greeting-request-inbox-and-upgrade`](./greeting-request-inbox-and-upgrade/spec.md)：会话升级、幂等与关注状态不变均有 API 集成证据。
- [`session-audit-observability`](./session-audit-observability/spec.md)：定义“会话审计可观测性”的可观察主路径、失败语义及父能力交接。
- [`session-governance-actions`](./session-governance-actions/spec.md)：定义“会话治理动作”的可观察主路径、失败语义及父能力交接。

## 5. 能力要求

<a id="req-001"></a>
### REQ-001 关注状态机与关系能力位单一真相源

- RelationshipState 枚举、RelationshipCapabilityView、主页动作矩阵和会话入口都只消费 self/not_following/following/followed_by/mutual。
- 规格、契约、端侧 UI、Remote/Mock 和测试中不存在作为关系等级的旧字段。
- mutual 仅由双向 FollowEdge 派生，不持久化第二套关系实体。

<a id="req-002"></a>
### REQ-002 拉黑门禁级联与取消拉黑不自动恢复关系

- 创建 BlockEdge 幂等，并删除双方 FollowEdge、失效双方 pending GreetingRequest、发布 UserBlocked。
- 任一方向存在拉黑时，关注、打招呼、建会话、SendMessage、1v1 RTC 均由服务端拒绝。
- 取消拉黑只删除 BlockEdge 并发布 UserUnblocked，不恢复关注边和 blocked 请求。
- 既有 1v1 conversation 只读保留，不能继续发送新消息。

<a id="req-003"></a>
### REQ-003 打招呼请求箱与回复建正式私信

- 非 mutual 且未拉黑用户可发起一条 pending GreetingRequest，请求不进入普通会话列表。
- 同一 requester-target 只能存在一条 pending 请求，重复创建返回结构化错误。
- 接收方回复 pending 请求后创建或复用 1v1 conversation，并写入 promotedConversationId。
- 回复建会话不自动创建 FollowEdge，不改变 RelationshipState。

<a id="req-004"></a>
### REQ-004 私信与 1v1 RTC 服务端门禁不可绕过

- CreateConversation 对 direct 1v1 校验 mutual 或 replied greeting；非授权状态不创建 conversation。
- SendMessage 校验 conversation 成员、非 blocked、会话未只读；不依赖端侧按钮作为唯一防线。
- 1v1 RTC 发起校验 mutual 且未 blocked；非 mutual 或 blocked 返回 metadata 生成的结构化错误。
- 端侧按钮、输入区、错误态与服务端错误语义一致。

<a id="req-005"></a>
### REQ-005 关系治理 metadata 与端云 DTO 一致

- metadata、codegen、Go struct、Dart DTO 中不存在旧关系等级字段。
- CreateConversation、SendMessage、RTC 均定义 relationship/blocked 结构化错误码。
- UserBlocked/UserUnblocked、GreetingRequestReplied、MessageSent 事件字段可被端云测试引用。

<a id="req-006"></a>
### REQ-006 不因拉黑删除既有消息；既有会话只读保留，禁止继续发送

- 不因拉黑删除既有消息；既有会话只读保留，禁止继续发送。
- 前台可显示“互相关注”，但不得把 `mutual` 命名为另一个关系等级。
- `mutual` 不得被包装成好友、同好、密友、挚友等额外关系等级。
- 拉黑必须同时阻断关注、打招呼、建会话、发消息、RTC。
- 服务端必须强校验关系门禁；端侧按钮只做展示优化，不能作为唯一防线。
- 关系状态、主页按钮、会话入口、消息发送、RTC 发起必须共享同一份 `RelationshipCapabilityView` 语义。
- 打招呼必须频控、去重、幂等，并对重复 pending 返回结构化错误。
- FollowEdge、BlockEdge、GreetingRequest、Conversation 之间存在跨存储操作时，必须使用同事务或事件补偿保证最终一致。
- `block` 与 `follow` 并发时，拉黑门禁胜出；若出现先写关注后写拉黑，补偿任务必须清除关注边。
- 关系能力读模型允许缓存，但缓存失效不得晚于拉黑写入后的可观测一致性窗口。

## 6. 契约与依赖

- 上游能力：[`chat-conversation`](../spec.md) 声明的领域入口。
- 下游能力：本目录直接 Story 及其公开结果。
- canonical 引用：`quwoquan_service/contracts/metadata/_shared/types.yaml#RelationshipState`、`quwoquan_service/services/user-service/contracts/relationship/subject_follow/operations.yaml`、`quwoquan_service/services/user-service/contracts/relationship/persona_relationship/operations.yaml`、`quwoquan_service/services/user-service/contracts/relationship/greeting_request/operations.yaml`、`quwoquan_service/services/chat-service/contracts/chat/conversation/operations.yaml#CreateConversation`、`quwoquan_service/services/chat-service/contracts/chat/conversation/operations.yaml#SendMessage`
- 一致性要求：遵循本层或父 L1 DEC 声明的一致性边界。

## 7. 集成验收

<a id="sit-001"></a>
### SIT-001 关注状态机与关系能力位单一真相源

- GIVEN 执行“关注状态机与关系能力位单一真相源”所需的身份、输入与上游事实均有效。
- WHEN 参与者发起“关注状态机与关系能力位单一真相源”对应动作。
- THEN RelationshipState 枚举、RelationshipCapabilityView、主页动作矩阵和会话入口都只消费 self/not_following/following/followed_by/mutual。
- THEN 规格、契约、端侧 UI、Remote/Mock 和测试中不存在作为关系等级的旧字段。
- THEN mutual 仅由双向 FollowEdge 派生，不持久化第二套关系实体。

<a id="sit-002"></a>
### SIT-002 拉黑门禁级联与取消拉黑不自动恢复关系

- GIVEN 执行“拉黑门禁级联与取消拉黑不自动恢复关系”所需的身份、输入与上游事实均有效。
- WHEN 参与者发起“拉黑门禁级联与取消拉黑不自动恢复关系”对应动作。
- THEN 创建 BlockEdge 幂等，并删除双方 FollowEdge、失效双方 pending GreetingRequest、发布 UserBlocked。
- THEN 任一方向存在拉黑时，关注、打招呼、建会话、SendMessage、1v1 RTC 均由服务端拒绝。
- THEN 取消拉黑只删除 BlockEdge 并发布 UserUnblocked，不恢复关注边和 blocked 请求。
- THEN 既有 1v1 conversation 只读保留，不能继续发送新消息。

<a id="sit-003"></a>
### SIT-003 打招呼请求箱与回复建正式私信

- GIVEN 执行“打招呼请求箱与回复建正式私信”所需的身份、输入与上游事实均有效。
- WHEN 参与者发起“打招呼请求箱与回复建正式私信”对应动作。
- THEN 非 mutual 且未拉黑用户可发起一条 pending GreetingRequest，请求不进入普通会话列表。
- THEN 同一 requester-target 只能存在一条 pending 请求，重复创建返回结构化错误。
- THEN 接收方回复 pending 请求后创建或复用 1v1 conversation，并写入 promotedConversationId。
- THEN 回复建会话不自动创建 FollowEdge，不改变 RelationshipState。

<a id="sit-004"></a>
### SIT-004 私信与 1v1 RTC 服务端门禁不可绕过

- GIVEN 执行“私信与 1v1 RTC 服务端门禁不可绕过”所需的身份、输入与上游事实均有效。
- WHEN 参与者发起“私信与 1v1 RTC 服务端门禁不可绕过”对应动作。
- THEN CreateConversation 对 direct 1v1 校验 mutual 或 replied greeting；非授权状态不创建 conversation。
- THEN SendMessage 校验 conversation 成员、非 blocked、会话未只读；不依赖端侧按钮作为唯一防线。
- THEN 1v1 RTC 发起校验 mutual 且未 blocked；非 mutual 或 blocked 返回 metadata 生成的结构化错误。
- THEN 端侧按钮、输入区、错误态与服务端错误语义一致。

<a id="sit-005"></a>
### SIT-005 关系治理 metadata 与端云 DTO 一致

- GIVEN 执行“关系治理 metadata 与端云 DTO 一致”所需的身份、输入与上游事实均有效。
- WHEN 参与者发起“关系治理 metadata 与端云 DTO 一致”对应动作。
- THEN metadata、codegen、Go struct、Dart DTO 中不存在旧关系等级字段。
- THEN CreateConversation、SendMessage、RTC 均定义 relationship/blocked 结构化错误码。
- THEN UserBlocked/UserUnblocked、GreetingRequestReplied、MessageSent 事件字段可被端云测试引用。
