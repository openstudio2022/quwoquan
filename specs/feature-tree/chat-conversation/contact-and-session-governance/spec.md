# L2 规格：contact-and-session-governance — 关注、拉黑与私信治理

> **层级**：L2_business_capability（隶属 L1 `chat-conversation`）
> **状态**：specified

## 0. 一句话定义

本能力只使用一个社交关系概念：`关注`。`互相关注`只是两条关注边同时存在时的派生状态，不另起用户概念；`拉黑`是最高优先级门禁；`打招呼 / 私信 / 会话`是消息流程，不是关系等级。本能力冻结关注、拉黑、打招呼、正式私信与 1v1 音视频之间的状态迁移和服务端门禁，避免关系命名二义、请求箱污染普通会话列表，以及端侧按钮与服务端权限漂移。

## 1. 背景与动机

当前聊天与用户关系治理存在五类断点：

1. 文档和代码中并存多套关系词，用户与实现均无法判断唯一真相。
2. 拉黑当前只作为端侧能力位遮罩，服务端会话、消息、RTC 仍缺强校验。
3. 打招呼请求箱在契约中存在，但云侧路由、状态机与升级正式会话链路未形成闭环。
4. `CreateConversation` 与 `SendMessage` 缺关系门禁，单向关注或被拉黑场景可绕过 UI 建会话或发消息。
5. 旧关系等级字段导致端云 DTO 与行为语义双轨。

本能力的职责是先冻结单一概念和状态迁移，再由用户主页、联系人列表、私信、RTC、群设置、交集推荐复用，不允许业务代码维护第二套关系判断表。

## 2. 目标用户

- 希望用最少名词理解“我是否关注了 TA、TA 是否关注我、能否发消息或通话”的普通用户。
- 希望先关注或打招呼、但不希望陌生消息污染普通会话列表的用户。
- 希望一键拉黑并立即阻断关注、打招呼、私信、音视频的用户。

## 3. 功能范围

### 3.1 In-Scope

| 编号 | 能力 | 说明 |
|------|------|------|
| G1 | 关注状态机 | 只保留 `self / not_following / following / followed_by / mutual`；`mutual` 仅表示两条关注边同时存在，不命名为新关系。 |
| G2 | 拉黑门禁 | `BlockEdge` 优先级高于关注、打招呼、会话与 RTC；任一方向存在拉黑即阻断所有新社交动作。 |
| G3 | 拉黑级联 | 创建拉黑边必须清除双方关注边，并使未回复打招呼请求失效；取消拉黑不自动恢复关注。 |
| G4 | 打招呼请求箱 | 非互相关注用户只能先打招呼；pending 请求不进入普通会话列表。 |
| G5 | 回复建正式私信 | 接收方回复打招呼后，服务端原子创建或复用 1v1 conversation，并写入 `promotedConversationId`。 |
| G6 | 正式私信门禁 | 互相关注可直接创建/进入 1v1 会话；打招呼回复后也可进入正式会话；其他状态不得直接创建 1v1 会话。 |
| G7 | 消息与 RTC 强校验 | `SendMessage` 与 1v1 RTC 发起必须在服务端校验未拉黑、会话合法；RTC 额外要求 `mutual`。 |
| G8 | 列表隔离与审计 | 请求箱、普通会话、关系门禁拒绝、拉黑级联均有审计事件与埋点。 |

### 3.2 Out-of-Scope

- 不定义任何除关注以外的关系等级。
- 不做关系积分、亲密度、勋章、自动推荐关系等级。
- 不做群对象拉黑；群治理仍仅提供退出群、举报消息和举报成员。
- 不因拉黑删除既有消息；既有会话只读保留，禁止继续发送。
- 不在本 L2 内定义群组空间、相册、文件库能力。

## 4. 单一概念与对象模型

### 4.1 RelationshipState

| 状态 | 判定 | 主页主动作 | 打招呼 | 1v1 正式私信 | 1v1 音视频 |
|------|------|------------|--------|--------------|------------|
| `self` | viewerId == targetId | 编辑资料 | — | — | — |
| `not_following` | 无双向关注边 | 关注 | 可发 | 不可直接创建 | 不可 |
| `following` | viewer 关注 target | 已关注 | 可发 | 不可直接创建 | 不可 |
| `followed_by` | target 关注 viewer | 回关 | 可发 | 不可直接创建 | 不可 |
| `mutual` | 两条关注边同时存在 | 已互相关注 | 不需要 | 可直接创建/进入 | 可 |

说明：

- 前台可显示“互相关注”，但不得把 `mutual` 命名为另一个关系等级。
- 关注边只存在于 `FollowEdge`；`RelationshipState` 是读侧派生结果，不单独持久化。
- 旧关系等级字段不再作为契约字段或业务判断依据。

### 4.2 BlockGate

| 门禁 | 判定 | 结果 |
|------|------|------|
| `isBlocked` | viewer 拉黑 target | viewer 不能关注、打招呼、创建会话、发消息、发起音视频；主页显示已拉黑治理态。 |
| `isBlockedBy` | target 拉黑 viewer | viewer 不能关注、打招呼、创建会话、发消息、发起音视频；不暴露可绕过入口。 |
| 任一方向拉黑 | `isBlocked || isBlockedBy` | 覆盖所有 `RelationshipState` 能力位。 |

拉黑写入规则：

1. 创建 `BlockEdge(blocker, blocked)` 必须幂等。
2. 写入成功后必须删除 `blocker -> blocked` 与 `blocked -> blocker` 两条 `FollowEdge`（存在则删，不存在则跳过）。
3. 写入成功后必须将双方之间 `pending` 的 `GreetingRequest` 标记为 `blocked`。
4. 写入成功后必须发布 `UserBlocked` 事件，供推荐、通知、会话可见性与审计消费。
5. 既有 1v1 会话不删除，消息只读保留；双方不能继续发送新消息或发起 1v1 RTC。

取消拉黑规则：

1. 删除 `BlockEdge(blocker, blocked)` 必须幂等。
2. 取消拉黑不自动恢复任何关注边。
3. 取消拉黑不自动恢复 blocked 状态的打招呼请求。
4. 取消拉黑后，双方回到由当前 `FollowEdge` 重新派生的关系状态；通常为 `not_following`。
5. 写入成功后必须发布 `UserUnblocked` 事件。

### 4.3 GreetingRequest

| 字段 | 类型 | 说明 |
|------|------|------|
| requestId | string | 请求唯一标识 |
| requesterId | string | 发起者 SubAccount |
| targetUserId | string | 接收者 SubAccount |
| content | string | 自定义打招呼内容 |
| status | enum | `pending / replied / ignored / blocked / cancelled / expired` |
| createdAt | datetime | 创建时间 |
| repliedAt | datetime? | 回复时间 |
| promotedConversationId | string? | 回复后创建或复用的 1v1 会话 ID |

创建规则：

1. 任一方向存在拉黑时拒绝创建。
2. `self` 拒绝创建。
3. `mutual` 不需要打招呼，直接进入正式私信。
4. 同一 requester-target 在 `pending` 状态下最多一条有效请求。
5. 被目标用户配置为不接收陌生打招呼时拒绝创建。

回复规则：

1. 只有 targetUserId 可回复。
2. 只有 `pending` 可回复。
3. 回复时必须在同一事务或可补偿流程中创建/复用 1v1 conversation，并将 `promotedConversationId` 写回请求。
4. 回复成功后请求状态变为 `replied`，conversation 进入普通会话列表。
5. 回复建会话不自动创建关注边；是否互相关注仍只由 `FollowEdge` 决定。

## 5. 状态迁移

### 5.1 关注迁移

| 动作 | 前置条件 | 副作用 | 结果 |
|------|----------|--------|------|
| `follow(target)` | 非 self；任一方向未拉黑 | 创建 `viewer -> target` FollowEdge；发布 `UserFollowed` | 由双向边派生为 `following` 或 `mutual` |
| `unfollow(target)` | 存在 `viewer -> target` FollowEdge | 删除该 FollowEdge；发布 `UserUnfollowed` | 由剩余边派生为 `not_following` 或 `followed_by` |
| `follow(target)` 重复 | 已存在 FollowEdge | 幂等返回当前状态 | 状态不变 |
| `unfollow(target)` 重复 | 不存在 FollowEdge | 幂等返回当前状态 | 状态不变 |

### 5.2 拉黑迁移

| 动作 | 前置条件 | 副作用 | 结果 |
|------|----------|--------|------|
| `block(target)` | 非 self | 创建 BlockEdge；删除双方 FollowEdge；pending 打招呼置 blocked；发布 UserBlocked | `isBlocked=true`，所有社交动作禁用 |
| `block(target)` 重复 | 已存在 BlockEdge | 幂等返回 blocked | 状态不变 |
| `unblock(target)` | 存在 BlockEdge | 删除 BlockEdge；发布 UserUnblocked；不恢复关注/打招呼 | 重新按 FollowEdge 派生，通常 `not_following` |
| 被对方拉黑后关注 | `isBlockedBy=true` | 拒绝，返回结构化错误 | 状态不变 |

### 5.3 私信迁移

| 动作 | 前置条件 | 副作用 | 结果 |
|------|----------|--------|------|
| `createDirectConversation(target)` | `mutual` 且未拉黑 | 创建或复用 1v1 conversation | 进入普通会话列表 |
| `createDirectConversation(target)` | 非 `mutual` 且无 replied greeting | 拒绝，提示先打招呼 | 不创建 conversation |
| `createGreeting(target)` | 非 self、非 mutual、未拉黑、无 pending | 创建 GreetingRequest | 进入请求箱，不进入普通会话列表 |
| `replyGreeting(request)` | pending 且未拉黑 | 状态变 `replied`；创建或复用 conversation；写 promotedConversationId | 进入普通会话列表 |
| `ignore/cancel/expireGreeting` | pending | 状态变 ignored/cancelled/expired | 不创建 conversation |
| `sendMessage(conversation)` | conversation 有效、成员有效、未拉黑 | 写消息并发布 MessageSent | 发送成功 |
| `sendMessage(conversation)` | 任一方向拉黑 | 拒绝，返回结构化错误 | 不写消息 |

### 5.4 RTC 迁移

| 动作 | 前置条件 | 副作用 | 结果 |
|------|----------|--------|------|
| `startOneToOneCall(target)` | `mutual` 且未拉黑 | 创建 RTC session | 可呼叫 |
| `startOneToOneCall(target)` | 非 `mutual` | 拒绝，返回结构化错误 | 不创建 session |
| `startOneToOneCall(target)` | 任一方向拉黑 | 拒绝，返回结构化错误 | 不创建 session |

## 6. 入口与交互基线

### 6.1 用户主页动作矩阵

| 状态 | 主动作 | 次动作 | 备注 |
|------|--------|--------|------|
| self | 编辑资料 | 管理身份 | 不出现社交动作 |
| not_following | 关注 | 打招呼 / 更多 | 不直接进入私信 |
| following | 已关注 | 打招呼 / 更多 | 不直接进入私信 |
| followed_by | 回关 | 打招呼 / 更多 | 回关后变为 `mutual` |
| mutual | 消息 / 语音 / 视频 | 更多 | 三个主动作等权；不得出现新关系名 |
| isBlocked | 取消拉黑 | 更多 | 不显示关注、打招呼、消息、通话 |
| isBlockedBy | 无可执行社交动作 | 更多 | 不暴露绕过入口 |

### 6.2 会话页动作矩阵

| 会话状态 | 输入区 | 顶部提示 | `+` 面板 |
|----------|--------|----------|----------|
| greeting_request | 无消息流输入 | 等待对方回复 | 不进入普通会话列表 |
| formal_conversation | 可发异步消息 | 无关系升级条 | 非 mutual 不展示 1v1 音视频 |
| mutual_conversation | 可发消息 | 无关系升级条 | 展示 1v1 语音/视频 |
| blocked_conversation | 禁止输入 | 已无法继续发送消息 | 隐藏 1v1 音视频 |

### 6.3 群聊治理边界

- 群聊设置页只保留会话管理与 `退出群聊`。
- 不提供拉黑群；拉黑始终是用户到用户的对象级门禁。
- 成员卡片/成员主页提供举报用户、拉黑用户。
- 消息长按菜单提供举报消息。

## 7. 业务约束

- 全 App 只允许一个关系概念：关注。
- `mutual` 不得被包装成好友、同好、密友、挚友等额外关系等级。
- 打招呼回复建会话不自动关注。
- 已存在正式会话不等于 `mutual`，也不解锁 1v1 音视频。
- 拉黑必须同时阻断关注、打招呼、建会话、发消息、RTC。
- 拉黑不删除既有消息；取消拉黑不自动恢复关注。
- 服务端必须强校验关系门禁；端侧按钮只做展示优化，不能作为唯一防线。
- 关系状态、主页按钮、会话入口、消息发送、RTC 发起必须共享同一份 `RelationshipCapabilityView` 语义。

## 8. 非功能要求

### 8.1 免骚扰

- 打招呼默认进入请求箱，不污染普通聊天列表。
- 用户可配置是否接收非互相关注用户的打招呼。
- 打招呼必须频控、去重、幂等，并对重复 pending 返回结构化错误。

### 8.2 一致性

- FollowEdge、BlockEdge、GreetingRequest、Conversation 之间存在跨存储操作时，必须使用同事务或事件补偿保证最终一致。
- `block` 与 `follow` 并发时，拉黑门禁胜出；若出现先写关注后写拉黑，补偿任务必须清除关注边。
- 关系能力读模型允许缓存，但缓存失效不得晚于拉黑写入后的可观测一致性窗口。

### 8.3 可观测

必须记录以下事件与指标：

- 关注成功 / 取消关注 / 互相关注形成 / 互相关注解除。
- 拉黑成功 / 取消拉黑 / 拉黑阻断关注 / 拉黑阻断打招呼 / 拉黑阻断消息 / 拉黑阻断 RTC。
- 打招呼发送率、回复率、忽略率、过期率、重复 pending 拦截率。
- 非互相关注建会话拒绝率、SendMessage 门禁拒绝率、RTC 门禁拒绝率。

### 8.4 SLO

- 关系能力读取 p95 ≤ 150ms。
- 拉黑写入到关注/打招呼/消息/RTC 门禁生效 p95 ≤ 1s。
- 打招呼回复到正式会话可见 p95 ≤ 2s。
- SendMessage 门禁校验额外耗时 p95 ≤ 20ms。

## 9. 与下游特性的边界

| 特性 | 依赖关系 | 本特性提供 |
|------|----------|------------|
| `realtime-call` | 消费 `mutual + !blocked` 门禁 | 是否可显示和发起 1v1 通话；服务端拒绝错误语义 |
| `group-settings` | 消费对象级拉黑边界 | 群聊只退出群，不拉黑群；成员卡片拉黑用户 |
| `user profile` | 消费关注状态与 BlockGate | 主页动作矩阵 |
| `chat list/detail` | 消费请求箱与正式会话边界 | 请求箱不进普通会话；blocked 会话只读 |
| `intersection-unified-experience` | 消费关注边事实 | 共同关注、互相关注、共同关系证据；不新增关系名 |

## 10. 进入开发阻塞定义

以下任一项未完成，不得进入实现：

1. 规格、术语表、acceptance 中仍出现作为关系等级的旧字段或旧概念。
2. `RelationshipCapabilityView` 未定义 `isBlocked / isBlockedBy / canFollow / canGreet / canCreateDirectConversation / canSendMessage / canStartVoiceCall / canStartVideoCall` 的唯一语义。
3. `BlockEdge` 未定义删除双方 FollowEdge、失效 pending GreetingRequest、发布事件与取消拉黑不恢复关注的规则。
4. `CreateConversation`、`SendMessage`、RTC 发起缺服务端关系门禁与结构化错误码。
5. `GreetingRequest` 缺 pending 唯一性、回复建会话、幂等和频控验收。
6. acceptance 未列出 SIT/GWT/contract、T1-T4 证据和磁盘测试路径。

## 11. 验收重点

### T1

- 关系状态枚举与字段契约只保留关注状态、拉黑门禁和消息流程字段。
- 错误码、事件、DTO、路径、operation/surface 均来自 metadata。

### T2

- 主页动作矩阵、请求箱、正式会话、blocked 会话四态正确。
- 端侧不出现旧关系词和旧升级入口。

### T3

- follow / unfollow / block / unblock / greeting / create direct conversation / send message / RTC 发起在端云集成环境按状态机运行。
- 服务端门禁不能被绕过。

### T4

- 真实用户旅程覆盖：关注 → 打招呼 → 回复建会话 → 互相关注 → 1v1 通话 → 拉黑 → 禁止发送/通话 → 取消拉黑后重新关注。
