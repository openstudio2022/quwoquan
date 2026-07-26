# L1 Design：聊天与会话 (`chat-conversation`)

> 对应规格：[L1 spec](./spec.md)

## 1. 背景与设计目标

- 设计目标：让用户在 1v1 与大群会话中可靠发送、接收、同步和治理消息，并在同一会话上下文完成实时通话；容量、权限和失败恢复均保持可观察。

## 2. 领域模型与所有权

- authoritative ownership：拥有 `Conversation`、会话成员投影、`Message`、投递/已读回执、会话治理状态和 `CallSession` 的生命周期与写入决定权。
- write boundary：只能通过本领域公开 command 修改其拥有事实。
- 非本域对象：不拥有其他 L1 的事实；跨域协作必须使用对方公开 command、query、projection 或 event。
- 非本域对象：不复制 metadata 中的字段、path、错误码和 wire 语义。

## 3. 上下文边界与协作

- [`JNY-003 / SCN-008`](../spec.md#scn-008) — 在“评论互动与回流”中，创建或复用 Conversation，维护 Membership、Message、Receipt 与通话信令，并交付可恢复会话终态。
- [`JNY-005 / SCN-011`](../spec.md#scn-011) — 在“全局搜索查询与筛选”中，创建或复用 Conversation，维护 Membership、Message、Receipt 与通话信令，并交付可恢复会话终态。
- [`JNY-007 / SCN-012`](../spec.md#scn-012) — 在“1v1 私信与打招呼升级”中，创建或复用 Conversation，维护 Membership、Message、Receipt 与通话信令，并交付可恢复会话终态。
- [`JNY-007 / SCN-013`](../spec.md#scn-013) — 在“私建群、圈子群、组织节点群与主页相关群入口”中，创建或复用 Conversation，维护 Membership、Message、Receipt 与通话信令，并交付可恢复会话终态。
- [`JNY-007 / SCN-015`](../spec.md#scn-015) — 在“小趣作为会话成员参与消息”中，创建或复用 Conversation，维护 Membership、Message、Receipt 与通话信令，并交付可恢复会话终态。
- [`JNY-007 / SCN-016`](../spec.md#scn-016) — 在“会话内音视频通话与离线来电可靠送达”中，创建或复用 Conversation，维护 Membership、Message、Receipt 与通话信令，并交付可恢复会话终态。
- [`JNY-008 / SCN-014`](../spec.md#scn-014) — 在“实体主页到圈子、组织节点、群单元与会话协作”中，创建或复用 Conversation，维护 Membership、Message、Receipt 与通话信令，并交付可恢复会话终态。
- [`JNY-009 / SCN-018`](../spec.md#scn-018) — 在“群聊话题理解与会话内回复”中，创建或复用 Conversation，维护 Membership、Message、Receipt 与通话信令，并交付可恢复会话终态。

## 4. 架构与数据流

- [`chat-experience-optimization`](./chat-experience-optimization/spec.md)：统一趣聊入口、会话详情与群聊管理的交互和状态
- [`commercial-message-system`](./commercial-message-system/spec.md)：以商用发布为目标，验证消息页、联系页、群主页、交集、通知和真实云端数据的一致性。
- [`contact-and-session-governance`](./contact-and-session-governance/spec.md)：以“关注”为唯一关系概念，验证关注状态、拉黑门禁、打招呼请求箱、正式私信与 1v1 RTC 的端云一致性。
- [`group-creation-member-management`](./group-creation-member-management/spec.md)：私建群创建、后续成员增删、角色治理与群设置在同一 Conversation/ConversationMembership 聚合边界内形成可商用闭环。
- [`list-detail-message-delivery`](./list-detail-message-delivery/spec.md)：保证消息从发送、确认、重试到列表与详情展示的一致性
- [`realtime-call`](./realtime-call/spec.md)：让用户在满足关系与成员权限时发起、接听、拒绝、取消和结束 1v1 或不超过 32 人的实时音视频通话，并通过同一 `CallSession/CallParticipant` 状态机、realtime-gateway 信令、LiveKit 媒体和会话记录获得可恢复结果。
- 工程边界由 spec 的“工程归属”声明；设计不复制具体实现文件。

## 5. 关键决策

<a id="dec-001"></a>
### DEC-001 Conversation 与 Membership 是消息状态的唯一写入边界
- 决策：Conversation 与 Membership 是消息状态的唯一写入边界。
- 理由：让用户在 1v1 与大群会话中可靠发送、接收、同步和治理消息，并在同一会话上下文完成实时通话；容量、权限和失败恢复均保持可观察。
- 被否决方案：由调用方、页面或脚本复制本层状态并绕过公开契约。
- 约束与影响：实现只能细化对应规格与 canonical contract；冲突时先修正规格或契约。
- 关联要求：`REQ-001`
- 关联能力：[`chat-experience-optimization`](./chat-experience-optimization/spec.md)、[`commercial-message-system`](./commercial-message-system/spec.md)、[`contact-and-session-governance`](./contact-and-session-governance/spec.md)、[`group-creation-member-management`](./group-creation-member-management/spec.md)、[`list-detail-message-delivery`](./list-detail-message-delivery/spec.md)、[`realtime-call`](./realtime-call/spec.md)

## 6. 质量与运行约束

- canary deployment → 监控 p99/错误率/seq gap 24h。
- 回退至上一已验证制品与配置快照；prod 禁止切换 mock 数据源。
- `.github/workflows/` 中 CI 配置覆盖 chat-service。

## 7. 失败与恢复

- 失败类型：权限拒绝、依赖超时、版本冲突或持久化失败。
- 可见结果：调用方收到可区分的 canonical failure 或规格明确允许的降级结果；任何失败均不写入成功事实。
- 恢复动作：按 canonical recovery action 重试、刷新或回滚到上一份已验证配置。
- 禁止 fallback：不得使用 Mock、旧 wire、双读双写或跨域直写伪造成功。
