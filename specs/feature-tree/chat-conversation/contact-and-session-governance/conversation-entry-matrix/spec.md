# L3 Story：conversation-entry-matrix

## 最小价值点

让主页、联系人、请求箱和既有会话入口共享同一份关系能力语义，并由服务端对建会话、发消息和一对一通话执行不可绕过的关注/拉黑门禁。

## 归属

- 领域服务：`chat-conversation`
- 业务能力：`contact-and-session-governance`
- 关联 Journey / Scenario：`message-social-connection / message-direct-and-greeting-upgrade`

## 行为范围

### In Scope

- `self / not_following / following / followed_by / mutual` 五态入口矩阵。
- `RelationshipCapabilityView` 驱动端侧动作展示。
- direct conversation 创建、消息发送和一对一 RTC 的服务端关系门禁。
- 拉黑级联后既有会话只读、取消拉黑不恢复关注。

### Out of Scope

- 群聊成员治理与群对象拉黑。
- 额外好友等级、亲密度或关系积分。
- GreetingRequest 请求箱内部状态机。

## 行为规则

- `mutual && !blocked` 可直接创建或复用 direct conversation。
- replied GreetingRequest 可由受控升级流程创建或复用 direct conversation，但不解锁一对一 RTC。
- 非 mutual 且无 replied GreetingRequest 时，普通建会话必须返回 `greeting_required`。
- 任一方向拉黑时，关注、建会话、发消息和一对一 RTC 均被服务端拒绝；已有消息只读保留。
- 端侧按钮只消费能力位，不承担唯一授权责任。

## 接口契约

- 关系能力：`quwoquan_service/contracts/metadata/user/persona_relationship/**`
- 会话与消息：`quwoquan_service/contracts/metadata/messages/conversation/**`
- 一对一通话：`quwoquan_service/contracts/metadata/rtc/call_session/**`

## 验收关注点

- 能力位与服务端授权保持同源。
- 拉黑写入到全部门禁生效 p95 不高于 1 秒。
- SendMessage 关系门禁额外耗时 p95 不高于 20 毫秒。
- 所有拒绝使用 metadata 生成的结构化错误并保留 request/trace id。
