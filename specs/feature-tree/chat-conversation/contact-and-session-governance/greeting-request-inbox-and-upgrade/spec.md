# L3 Story：greeting-request-inbox-and-upgrade

## 最小价值点

让非互相关注用户的首次联系进入独立打招呼请求箱，并在接收方回复后幂等升级为正式一对一会话，避免未获回应的陌生请求污染普通消息列表。

## 归属

- 领域服务：`chat-conversation`
- 业务能力：`contact-and-session-governance`
- 关联 Journey / Scenario：`message-social-connection / message-direct-and-greeting-upgrade`

## 行为范围

### In Scope

- 创建、查看、回复、忽略、撤回和过期 `GreetingRequest`。
- pending 请求与普通会话列表隔离。
- 回复时创建或复用正式 direct conversation，并写回 `promotedConversationId`。
- 拉黑、重复 pending、频控和接收偏好的服务端门禁。

### Out of Scope

- 关注关系的自动创建或额外关系等级。
- 正式会话中的消息收发与回执。
- 外部 APNs/FCM 推送交付。

## 行为规则

- Given：双方不是互相关注、任一方向未拉黑且接收方允许陌生打招呼。
- When：发起方发送一条打招呼请求。
- Then：请求进入独立收发箱，不创建普通会话。
- Given：接收方收到 pending 请求。
- When：接收方回复。
- Then：服务端创建或复用正式 direct conversation，将请求置为 replied，并写回 `promotedConversationId`；关注状态保持不变。

## 接口契约

- metadata：`quwoquan_service/contracts/metadata/user/greeting_request/**`
- 会话升级：`quwoquan_service/contracts/metadata/messages/conversation/service.yaml`
- 页面：`greetingInbox` surface / `/chat/greetings`
- 错误：统一消费 metadata 生成的 GreetingRequest 与 Conversation 错误语义。

## 验收关注点

- pending 唯一性、幂等重放、拉黑级联、频控与状态迁移不可绕过。
- 回复到正式会话可见 p95 不高于 2 秒。
- 收到侧、发出侧和所有终态均有结构化反馈与可恢复动作。
