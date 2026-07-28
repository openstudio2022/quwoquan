# L1 Domain Service：聊天与会话 (`chat-conversation`)

> 一句话定位：让用户在 1v1 与群会话中可靠交换消息、管理会话并完成实时通话协作。

## 1. 目标与用户价值

让用户在 1v1 与大群会话中可靠发送、接收、同步和治理消息，并在同一会话上下文完成实时通话；容量、权限和失败恢复均保持可观察。

## 2. 领域边界

### 本领域拥有

- 拥有 `Conversation`、会话成员投影、`Message`、投递/已读回执、会话治理状态和 `CallSession` 的生命周期与写入决定权。
- 只能通过本领域公开 command 修改其拥有事实。

### 本领域不拥有

- 不拥有其他 L1 的事实；跨域协作必须使用对方公开 command、query、projection 或 event。
- 不复制 metadata 中的字段、path、错误码和 wire 语义。

### 上下游协作

- 上游：AppRoot Journey 与公开输入事实。
- 下游：直接 L2 能力以及协作 L1 的公开结果。
- 跨域写入：目标领域公开 command；禁止直写目标存储。
- 跨域读取：目标领域公开 query/projection。

## 3. Journey / Scenario 职责

- [`JNY-003 / SCN-008`](../spec.md#scn-008)
  - 本领域负责：在“评论互动与回流”中，创建或复用 Conversation，维护 Membership、Message、Receipt 与通话信令，并交付可恢复会话终态。
  - 进入条件：`discovery-content` 已交付其公开结果。
  - 交付给下游的结果：创建或复用 Conversation，维护 Membership、Message、Receipt 与通话信令，并交付可恢复会话终态，形成该场景中本领域负责的终态。
  - 不负责：不决定账号关系、圈子成员资格、助手推理或媒体传输事实。
- [`JNY-005 / SCN-011`](../spec.md#scn-011)
  - 本领域负责：在“全局搜索查询与筛选”中，创建或复用 Conversation，维护 Membership、Message、Receipt 与通话信令，并交付可恢复会话终态。
  - 进入条件：`circle-community` 已交付其公开结果。
  - 交付给下游的结果：创建或复用 Conversation，维护 Membership、Message、Receipt 与通话信令，并交付可恢复会话终态，供 `shared-homepage-network` 继续处理。
  - 不负责：不决定账号关系、圈子成员资格、助手推理或媒体传输事实。
- [`JNY-007 / SCN-012`](../spec.md#scn-012)
  - 本领域负责：在“1v1 私信与打招呼升级”中，创建或复用 Conversation，维护 Membership、Message、Receipt 与通话信令，并交付可恢复会话终态。
  - 进入条件：用户发起“1v1 私信与打招呼升级”且身份、输入与权限前置成立。
  - 交付给下游的结果：创建或复用 Conversation，维护 Membership、Message、Receipt 与通话信令，并交付可恢复会话终态，供 `user-identity-profile-relationship` 继续处理。
  - 不负责：不决定账号关系、圈子成员资格、助手推理或媒体传输事实。
- [`JNY-007 / SCN-013`](../spec.md#scn-013)
  - 本领域负责：在“私建群、圈子群、组织节点群与主页相关群入口”中，创建或复用 Conversation，维护 Membership、Message、Receipt 与通话信令，并交付可恢复会话终态。
  - 进入条件：用户发起“私建群、圈子群、组织节点群与主页相关群入口”且身份、输入与权限前置成立。
  - 交付给下游的结果：创建或复用 Conversation，维护 Membership、Message、Receipt 与通话信令，并交付可恢复会话终态，供 `circle-community` 继续处理。
  - 不负责：不决定账号关系、圈子成员资格、助手推理或媒体传输事实。
- [`JNY-007 / SCN-015`](../spec.md#scn-015)
  - 本领域负责：在“小趣作为会话成员参与消息”中，创建或复用 Conversation，维护 Membership、Message、Receipt 与通话信令，并交付可恢复会话终态。
  - 进入条件：用户发起“小趣作为会话成员参与消息”且身份、输入与权限前置成立。
  - 交付给下游的结果：创建或复用 Conversation，维护 Membership、Message、Receipt 与通话信令，并交付可恢复会话终态，供 `assistant-run-learning` 继续处理。
  - 不负责：不决定账号关系、圈子成员资格、助手推理或媒体传输事实。
- [`JNY-007 / SCN-016`](../spec.md#scn-016)
  - 本领域负责：在“会话内音视频通话与离线来电可靠送达”中，创建或复用 Conversation，维护 Membership、Message、Receipt 与通话信令，并交付可恢复会话终态。
  - 进入条件：用户发起“会话内音视频通话与离线来电可靠送达”且身份、输入与权限前置成立。
  - 交付给下游的结果：创建或复用 Conversation，维护 Membership、Message、Receipt 与通话信令，并交付可恢复会话终态，供 `user-identity-profile-relationship` 继续处理。
  - 不负责：不决定账号关系、圈子成员资格、助手推理或媒体传输事实。
- [`JNY-008 / SCN-014`](../spec.md#scn-014)
  - 本领域负责：在“实体主页到圈子、组织节点、群单元与会话协作”中，创建或复用 Conversation，维护 Membership、Message、Receipt 与通话信令，并交付可恢复会话终态。
  - 进入条件：`shared-homepage-network` 已交付其公开结果。
  - 交付给下游的结果：创建或复用 Conversation，维护 Membership、Message、Receipt 与通话信令，并交付可恢复会话终态，供 `discovery-content` 继续处理。
  - 不负责：不决定账号关系、圈子成员资格、助手推理或媒体传输事实。
- [`JNY-009 / SCN-018`](../spec.md#scn-018)
  - 本领域负责：在“群聊话题理解与会话内回复”中，创建或复用 Conversation，维护 Membership、Message、Receipt 与通话信令，并交付可恢复会话终态。
  - 进入条件：`assistant-run-learning` 已交付其公开结果。
  - 交付给下游的结果：创建或复用 Conversation，维护 Membership、Message、Receipt 与通话信令，并交付可恢复会话终态，供 `runtime` 继续处理。
  - 不负责：不决定账号关系、圈子成员资格、助手推理或媒体传输事实。
- [`JNY-009 / SCN-019`](../spec.md#scn-019)
  - 本领域负责：在“搜索 handoff 与统一 grounding”中，创建或复用 Conversation，维护 Membership、Message、Receipt 与通话信令，并交付可恢复会话终态。
  - 进入条件：`discovery-content` 已交付其公开结果。
  - 交付给下游的结果：创建或复用 Conversation，维护 Membership、Message、Receipt 与通话信令，并交付可恢复会话终态，供 `shared-homepage-network` 继续处理。
  - 不负责：不决定账号关系、圈子成员资格、助手推理或媒体传输事实。
- [`JNY-009 / SCN-020`](../spec.md#scn-020)
  - 本领域负责：在“小趣主动订阅与用户/会话投递”中，创建或复用 Conversation，维护 Membership、Message、Receipt 与通话信令，并交付可恢复会话终态。
  - 进入条件：`assistant-run-learning` 已交付其公开结果。
  - 交付给下游的结果：创建或复用 Conversation，维护 Membership、Message、Receipt 与通话信令，并交付可恢复会话终态，供 `runtime` 继续处理。
  - 不负责：不决定账号关系、圈子成员资格、助手推理或媒体传输事实。
- [`JNY-011 / SCN-026`](../spec.md#scn-026)
  - 本领域负责：在“对象页交集行动深化（同趣围观到破冰升级）”中，创建或复用 Conversation，维护 Membership、Message、Receipt 与通话信令，并交付可恢复会话终态。
  - 进入条件：`recommendation-platform` 已交付其公开结果。
  - 交付给下游的结果：创建或复用 Conversation，维护 Membership、Message、Receipt 与通话信令，并交付可恢复会话终态，形成该场景中本领域负责的终态。
  - 不负责：不决定账号关系、圈子成员资格、助手推理或媒体传输事实。
- [`JNY-011 / SCN-027`](../spec.md#scn-027)
  - 本领域负责：在“附近同趣·结伴同行·线下局”中，创建或复用 Conversation，维护 Membership、Message、Receipt 与通话信令，并交付可恢复会话终态。
  - 进入条件：`user-identity-profile-relationship` 已交付其公开结果。
  - 交付给下游的结果：创建或复用 Conversation，维护 Membership、Message、Receipt 与通话信令，并交付可恢复会话终态，形成该场景中本领域负责的终态。
  - 不负责：不决定账号关系、圈子成员资格、助手推理或媒体传输事实。
- [`JNY-011 / SCN-028`](../spec.md#scn-028)
  - 本领域负责：在“派生称谓与联系人标签驱动连接”中，创建或复用 Conversation，维护 Membership、Message、Receipt 与通话信令，并交付可恢复会话终态。
  - 进入条件：`user-identity-profile-relationship` 已交付其公开结果。
  - 交付给下游的结果：创建或复用 Conversation，维护 Membership、Message、Receipt 与通话信令，并交付可恢复会话终态，供 `recommendation-platform` 继续处理。
  - 不负责：不决定账号关系、圈子成员资格、助手推理或媒体传输事实。

## 4. 业务能力

- [`chat-experience-optimization`](./chat-experience-optimization/spec.md)：统一趣聊入口、会话详情与群聊管理的交互和状态
- [`commercial-message-system`](./commercial-message-system/spec.md)：以商用发布为目标，验证消息页、联系页、群主页、交集、通知和真实云端数据的一致性。
- [`contact-and-session-governance`](./contact-and-session-governance/spec.md)：以“关注”为唯一关系概念，验证关注状态、拉黑门禁、打招呼请求箱、正式私信与 1v1 RTC 的端云一致性。
- [`group-creation-member-management`](./group-creation-member-management/spec.md)：私建群创建、后续成员增删、角色治理与群设置在同一 Conversation/ConversationMembership 聚合边界内形成可商用闭环。
- [`list-detail-message-delivery`](./list-detail-message-delivery/spec.md)：保证消息从发送、确认、重试到列表与详情展示的一致性
- [`realtime-call`](./realtime-call/spec.md)：让用户在满足关系与成员权限时发起、接听、拒绝、取消和结束 1v1 或不超过 32 人的实时音视频通话，并通过同一 `CallSession/CallParticipant` 状态机、realtime-gateway 信令、LiveKit 媒体和会话记录获得可恢复结果。

## 5. 领域要求

<a id="req-001"></a>
### REQ-001 chat conversation 领域边界验收

- 领域边界、上下游依赖、工程映射和服务治理清晰。

<a id="req-002"></a>
### REQ-002 商用消息体系真实数据边界验收

- 消息页与联系页作为消息模块内两个独立一级页面状态，底栏保持五项不变。
- 消息、联系、群主页、交集和通知事实均来自 metadata/codegen 对齐的 Remote DTO 与真实服务 read model。
- 生产路径不依赖 App Mock、PrototypeBundle、mock-user、memory store、noop resolver 或退役字段。
- 群头像由服务端预合成 avatarUrl 驱动，App 不触发群成员九宫格 fallback。
- 会话/成员/用户态命令以 actor-scoped Idempotency-Key 回执 + 事务 outbox 提交；目标态已满足持久化 no-op 回执并重放原结果。
- SendMessage 幂等单轨（Idempotency-Key 即 clientMsgId），端侧持久化待发队列跨重启按原 clientMsgId 自动重发。
- inbox 未读真相源是服务端投影（MessageSent 经 outbox 由 projector 原子推进；已读水位单调），App 本地 +1 仅为展示提示。

<a id="req-003"></a>
### REQ-003 `encrypted`：保留给加密或密信能力

- `encrypted`：保留给加密或密信能力；未接入 chat-service 主链前不得作为首发主推能力。
- alpha/beta/gamma/prod App 只装配 Remote chat typed ports；对象级 typed double 仅存在 local_contract 测试树，禁止 runner/UAT override 与运行时 Mock/Remote 切换。
- 会话与消息接口统一 `{ items, nextCursor }` 分页协议
- 聊天全链路必须透传 `X-Request-Id` / `X-Trace-Id` / `X-Client-Page-Id` / `X-Client-Session-Id`
- Message.seq 为服务端唯一真相，客户端禁止自行生成 seq
- 成员变更事件必须同步触发 ChatInbox 读模型更新
- 端侧 chat 页面必须在 `lib/ui/chat/` 下，禁止 `lib/features/chat/`

## 6. 领域验收

<a id="dom-001"></a>
### DOM-001 chat conversation 领域边界验收

- 条件：本领域收到有效输入且前置领域事实成立。
- 可观察结果：领域边界、上下游依赖、工程映射和服务治理清晰。
- 禁止结果：不得绕过本领域公开 command/query/event 写入其拥有事实。

<a id="dom-002"></a>
### DOM-002 商用消息体系真实数据边界验收

- 条件：本领域收到有效输入且前置领域事实成立。
- 可观察结果：消息页与联系页作为消息模块内两个独立一级页面状态，底栏保持五项不变。
- 消息、联系、群主页、交集和通知事实均来自 metadata/codegen 对齐的 Remote DTO 与真实服务 read model。
- 生产路径不依赖 App Mock、PrototypeBundle、mock-user、memory store、noop resolver 或退役字段。
- 群头像由服务端预合成 avatarUrl 驱动，App 不触发群成员九宫格 fallback。
- 会话、成员与用户态命令以 actor-scoped `Idempotency-Key` 回执和事务 outbox 原子提交；重复请求返回持久化的原结果。
- SendMessage 幂等单轨（Idempotency-Key 即 clientMsgId），端侧持久化待发队列跨重启按原 clientMsgId 自动重发。
- inbox 未读真相源是服务端投影：MessageSent 经 outbox 由 projector 原子推进，已读水位单调；App 本地 +1 仅为展示提示。
- 禁止结果：Entity/Homepage 不直接拥有 conversation，只通过 related groups 进入群聊。
- Circle 是成员池，Group/CircleGroup 是协作单元，Conversation 只负责消息。
- Contact 与 Intersection 均为云端聚合 read model，App 不拼业务事实。
- chat 云侧搜索无入口，本地 SQLite 检索是唯一搜索路径。
- 实时下行推送依赖 realtime-gateway（B10），本域保证 long-poll/主动 sync 可靠路径。

## 7. 工程归属

- App：`quwoquan_app/lib/ui/chat`、`quwoquan_app/lib/cloud/services/chat`
- Service：`quwoquan_service/services/chat-service`、`quwoquan_service/services/notification-service`、`quwoquan_service/services/rtc-service`
- 测试：
  - `local_contract`：`quwoquan_service/services/chat-service/tests`
  - `api_integration`：`quwoquan_service/services/chat-service/tests`
  - `user_acceptance`：`quwoquan_ops/tests/acceptance/user_acceptance`

## 8. 开放事项

<a id="open-001"></a>
### OPEN-001 chat conversation 领域边界验收

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`；目标：领域边界、上下游依赖、工程映射和服务治理清晰。
- 完成判定：`DOM-001` 对应行为满足且真实测试 `spec_ref` 有效

<a id="open-002"></a>
### OPEN-002 商用消息体系真实数据边界验收

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`；目标：消息页与联系页作为消息模块内两个独立一级页面状态，底栏保持五项不变。
- 完成判定：`DOM-002` 对应行为满足且真实测试 `spec_ref` 有效
