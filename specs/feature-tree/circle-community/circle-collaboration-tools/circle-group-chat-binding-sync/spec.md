# L3 Story：circle-group-chat-binding-sync

## 节点定位

- `L1_domain_service`: `circle-community`
- `L2_business_capability`: `circle-collaboration-tools`
- `L3_story`: `circle-group-chat-binding-sync`

## 目标与用户价值

CircleGroup 是群单元、成员与角色的权威对象；Conversation 只提供消息能力。用户加入、离开、
被移除、被授予管理员或群组归档后，聊天名册、Inbox 与实时页面必须在可观测时限内准确收敛，
不能出现“已是圈群成员却无法聊天”“已离群仍可看到/发送消息”或“Chat 群主篡改圈群角色”。

## In Scope

- `CircleGroupCreated` 通过 durable Stream 在 chat-service 原子 provision 唯一绑定 Conversation、
  创建 owner Chat member/UserState，并由 `CircleGroupConversationProvisioned` durable event 回写
  `CircleGroup.conversationId`。
- `CircleGroupMembershipActivated / Left / Removed / RoleChanged` 可重放投影到 Chat 成员名册；
  role 映射固定为 `owner → owner`、`manager → admin`、`member → member`。
- `CircleGroupArchived` 终止绑定 Conversation，删除所有 `ConversationUserState`、收敛 ChatInbox，
  并向现有成员发 terminal realtime 事件。
- CircleGroup 与 Chat 统一限制为 1000 active human members；容量满必须在 Circle membership
  事务中拒绝，不能在 Chat 异步投影阶段静默丢失。
- 所有消费者使用 Redis Stream consumer group、pending reclaim、source-event 幂等、受控重试、
  7 天 TTL DLQ、health/metrics/alert；成功持久化后才 ACK。
- 普通 Chat HTTP 的创建绑定字段、加人、移除、退群、转让群主、管理员、标题、公告、治理开关和
  解散不得改写圈群权威模型，绑定群统一返回 `CHAT.USER.circle_group_managed_by_circle`。

## Out of Scope

- CircleGroup 文件、公告、公开内容区本身的功能设计。
- 新增社交关系准入、邀请链接、二维码或跨圈迁移能力。
- 通过兼容读、双写、页面本地缓存或同步 RPC 迁移旧 `Circle.conversationId` 模型。

## 不变量

1. 任一 active CircleGroup 恰有一个 active 绑定 Conversation；二者用
   `CircleGroup.conversationId ⇄ Conversation.circleGroupId` 双向校验。
2. CircleGroupMembership 是圈群 human member 与 role 的唯一写模型，Chat 只是投影。
3. Stream 重复、reclaim、乱序与服务重启后不得产生第二 Conversation、第二 member、复活
   UserState，或错误降级 role。
4. 终态一经消费，迟到 MessageSent、settings 或本地缓存不得重建离群用户的 Inbox 可达性。
5. 任何 DLQ、超过 30 秒 pending、绑定延迟/名册偏差超过 SLO 都必须健康检查失败或触发告警，
   不能静默忽略。

## 三层测试映射

| 验收点 | local_contract | api_integration | user_acceptance |
| --- | --- | --- | --- |
| Stream envelope、幂等、ACK/DLQ、role 映射 | consumer/application 测试 | Redis + Mongo replay | — |
| 创建与双向绑定 | projection contract | Circle HTTP → Stream → Chat/Circle readback | 圈群页进入交流 |
| active/left/removed/role/archived | state-machine contract | 双服务真实存储与 Inbox/realtime | 双账号加入、离开、被移除 |
| 1000 容量与 Chat 旁路拒绝 | capacity/governance contract | 并发申请与 HTTP 错误码 | 管理页不显示危险入口 |
| 指标、健康、DLQ 告警 | metrics/health contract | `/metrics`、`/healthz` readback | gamma/prod release smoke |
