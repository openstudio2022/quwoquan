# L3 Scenario：group-member-roster-version-sync

## 节点定位

- `L1_capability`: `chat-conversation`
- `L2_journey`: `group-creation-member-management`
- `L3_scenario`: `group-member-roster-version-sync`

## 背景与动机

群成员展示、排序与多端同步此前存在端云/Mock 分叉、`ListMembers` 排序语义未冻结、实时推送易产生多人同时加入的事件风暴，且缺少统一的「版本/时间戳」供客户端增量拉取。本场景在 baseline 层收口：**展示名真相源、排序模式、合并推送、拉取对齐、建群与并发更新的云侧事务边界**。

## 目标用户

- 发起/管理群聊的普通用户与群主
- 被邀请入群、需在会话列表与信息页看到一致成员的其他成员

## 功能范围

### In Scope

- **成员展示名**：`ListMembers` / Mock 与云侧一致，返回**用户展示名**（可与联系人/资料一致）；**重名仅影响展示，身份以 `userId` 为准**（全应用唯一）。
- **ListMembers 排序**：支持两种模式，由 query 参数 `sort` 指定，枚举 `MemberListSort`：`joined_asc`（**默认**，加入顺序，先加入在前）、`display_name_asc`（展示名字典序，**并列时按 `userId` 升序**）。
- **云侧版本与时间戳**：`Conversation.membersRosterRevision`（单调递增）与 `Conversation.updatedAt` **仅在 chat-service 事务内**一并更新；客户端以二者与 `ListConversationTimestamps` / `GetConversation` 做增量判断。
- **事件合并**：同一群内短时间多条成员/群资料变更，**对外实时通道优先合并为 `ConversationRosterUpdated`**（负载含 `membersRosterRevision`、`updatedAt`、`aspects`）；`MemberJoined`/`MemberLeft` 保留为域内/审计用途，**不作为客户端主消费路径**（迁移期可双发，以设计为准）。
- **拉取路径**：客户端收到合并事件或发现 revision 落后时，按 **时间戳/版本** 拉取 `GetConversation` + `ListMembers`（及必要群设置），避免依赖未合并的逐条事件。
- **云侧事务边界**：
  - **创建群**（单端发起的 `CreateConversation`）：单事务内完成会话文档、群主成员、初始成员、`ConversationUserState`、**首版 `membersRosterRevision`/时间戳**；对外可发 `ConversationCreated` + **一条** `ConversationRosterUpdated`（或与 Created 合并策略在设计中选定，须唯一真相）。
  - **建群后更新**（加人、踢人、改群名、管理员/规则等）：**允许多端并发**；每项变更在**独立事务**中完成持久化并 **$inc`/递增 revision**，事务提交后进入合并推送窗口。
- **Mock**：`MockChatRepository` 必须与云契约对齐：`displayName` 为用户展示名（可与 `ChatMockData.nameFor` 等一致）、`ListMembers` 尊重 `sort`、维护 `membersRosterRevision` 与 `updatedAt`、模拟合并事件语义（至少在同一 `addMembers` 请求内合并为一次 roster 更新信号）。

### Out of Scope

- 用户自行修改「群内昵称」与资料彻底解耦的独立产品能力（若未来要做，需新 CR）
- 超大群（接近 500）下推送扇出的具体网关 sharding 实现细节（由 `realtime-gateway` 专项设计承接，本场景只规定合并与 revision 契约）

## 约束

- `userId` 为成员唯一标识；UI 去重、路由、权限一律基于 `userId`。
- `membersRosterRevision` 与 `updatedAt` **仅由服务端写入**，客户端禁止自创 revision。
- metadata 为 `sort` 枚举、`membersRosterRevision` 字段与 `ConversationRosterUpdated` 事件的唯一真相源。

## 非功能目标（及时性 / 性能）

- **及时性**：在线用户通过合并推送触发 UI 刷新，目标 P95 **< 500ms**（网关+Redis，不含弱网）；离线靠时间戳拉取，与现有会话同步防抖可并存，成员强一致场景下允许 **缩短防抖或按会话维度 bypass**（在 `/dev` 落具体阈值）。
- **性能**：合并推送 **单群单窗口至多 1 条** `ConversationRosterUpdated`（窗口默认 **50–100ms** 可配置）；拉取侧 **禁止** 每次事件全量 `listConversations`；仅对受影响 `conversationId` **定点** `GetConversation` + `ListMembers`（分页上限沿用契约）。

## 验收重点

1. 默认 `joined_asc` 与可选 `display_name_asc` 在契约测试与端侧调用均可验证。
2. 创建群与并发更新的事务边界在设计与合同测试中可区分验证。
3. `ConversationRosterUpdated` 与 revision 字段在 metadata、Go 常量、Publisher 白名单、App 实时 handler 链路可对齐（`/dev` 补齐实现）。

## T1~T4 映射

| 验收项 | T1 | T2 | T3 | T4 |
|--------|----|----|----|-----|
| metadata 字段/枚举/事件 | ✓ | | | |
| ListMembers sort 行为 | ✓ | ✓ | ✓ | |
| Mock 与 Remote 展示名一致 | | ✓ | ✓ | 抽样 |
| 合并推送 + revision 拉取 | ✓ | ✓ | ✓ | 双账号 |
