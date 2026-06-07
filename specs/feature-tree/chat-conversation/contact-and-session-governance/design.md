# 关注、拉黑与私信治理设计方案

## 设计动因

`contact-and-session-governance/spec.md` 已冻结单一关系概念：`关注`。现有端云基础有 `FollowEdge`、`BlockEdge`、`Conversation` 和部分能力位，但缺少三条闭环：

1. 拉黑写入后的关注边清理、请求失效、事件发布和服务端强门禁。
2. 打招呼请求箱到正式私信的升级语义。
3. 主页、会话、消息发送、RTC 发起共享同一份关系能力真相源。

本设计采用“关注边 + 拉黑门禁 + 请求箱对象 + 正式会话升级 + 能力位投影”的分层方案。`mutual` 仅表示两条关注边同时存在，不命名为额外关系等级。

## 上游输入评审

- `spec.md` 已冻结关注状态机、拉黑级联、请求箱边界、正式私信门禁和 RTC 服务端门禁。
- `realtime-call/spec.md` 需跟随本设计，把 1v1 门禁从旧关系词迁移为 `mutual + !blocked`。
- `group-settings` 继续只承担群会话设置与退出；拉黑是用户对象级门禁。
- 本 L2 不定义群组空间、相册和文件库。

## 对标输入分析

| 对标 | 借鉴 | 不借鉴 | 本设计落点 |
|------|------|--------|------------|
| 微信申请流程 | 请求箱与正式会话分层、先通过再进入稳定沟通 | 复制第三方关系等级 | `GreetingRequest` 未回复不进普通会话列表 |
| Instagram 私信请求 | 请求不污染主列表，由接收方决定是否升级 | 请求与正式私信长期并存 | 回复后创建或复用正式 1v1 conversation |
| Signal/WhatsApp 隐私门禁 | 对象级 block 服务端强阻断 | 仅端侧隐藏入口 | CreateConversation、SendMessage、RTC 均复核 block |
| 小红书/微博关注制 | 关注作为主要关系动作 | 额外好友等级 | FollowEdge 是唯一关系写侧真相源 |

## 方案对比

### 对比 1：打招呼是否直接创建 Conversation

#### 方案 A：直接创建正式会话

打招呼一发送就创建 `Conversation(type=direct)`，在列表中标记为“待回复”。

缺点：污染普通会话列表，Conversation 承载过多非聊天状态，拉黑/忽略/过期会污染主链。

#### 方案 B：独立 GreetingRequest，再升级 Conversation（选定）

未回复前使用独立请求对象；回复后创建或复用正式会话。

优点：请求箱与正式会话职责清晰，主聊天列表不被污染，服务端门禁更易统一。

### 对比 2：拉黑是否保留关注边

#### 方案 A：拉黑只作为遮罩

创建 BlockEdge 后不清理 FollowEdge，取消拉黑后隐式恢复旧关注状态。

缺点：用户以为已断开关系，系统却隐式恢复，推荐、交集和通知也会看到脏关系。

#### 方案 B：拉黑清理双方关注边（选定）

创建 BlockEdge 后删除双方 FollowEdge，取消拉黑不自动恢复关注。

优点：用户语义清楚，推荐/交集事实边干净，取消拉黑后需要重新关注，避免隐式复联。

### 对比 3：关系门禁放在哪层

#### 方案 A：页面层零散判断

页面隐藏按钮，但服务端不拦截。

缺点：可绕过，端云漂移。

#### 方案 B：能力位 + 服务端强校验（选定）

`RelationshipCapabilityView` 只负责读侧展示；CreateConversation、SendMessage、RTC 发起在服务端各自复核。

优点：用户界面与真实权限一致，越权入口无法绕过。

## 关键设计决策

### KD-1：唯一关系真相源

`FollowEdge` 是唯一关系写侧对象。读侧 `RelationshipState` 只派生：

```text
self
not_following
following
followed_by
mutual
```

禁止新增或保留旧关系等级字段。

### KD-2：BlockGate 级联

创建 `BlockEdge(blocker, blocked)` 时：

1. 幂等写入 BlockEdge。
2. 删除 `blocker -> blocked` 与 `blocked -> blocker` 两条 FollowEdge。
3. 将双方之间 pending GreetingRequest 标记为 `blocked`。
4. 发布 `UserBlocked`。
5. 既有 direct conversation 保留记录，但切成只读门禁态。

取消拉黑时：

1. 幂等删除 BlockEdge。
2. 发布 `UserUnblocked`。
3. 不恢复关注边，不恢复 blocked 请求。

### KD-3：RelationshipCapabilityView

统一输出读侧能力：

```text
relationState
isBlocked
isBlockedBy
canFollow
canUnfollow
canGreet
canCreateDirectConversation
canSendMessage
canStartVoiceCall
canStartVideoCall
hasPendingGreeting
hasFormalConversation
```

页面只消费能力位；服务端 API 仍必须复核权限。

### KD-4：请求箱对象

`GreetingRequest` 是未升级前的请求容器，状态：

```text
pending
replied
ignored
blocked
cancelled
expired
```

规则：

1. 任一方向拉黑拒绝创建。
2. `mutual` 不需要打招呼，直接进入正式私信。
3. 同一 requester-target 只允许一条 pending。
4. 回复 pending 请求时创建或复用 direct conversation，并写 `promotedConversationId`。
5. 回复建会话不自动创建关注边。

### KD-5：正式私信门禁

`CreateConversation(type=direct)` 只允许两类来源：

1. 双方 `mutual` 且未拉黑。
2. `GreetingRequest.status=replied` 的升级流程。

其他状态返回 metadata 生成的结构化错误。

`SendMessage` 必须校验：

1. 发送者是 conversation 成员。
2. direct conversation 双方任一方向未拉黑。
3. conversation 未处于只读门禁态。

### KD-6：RTC 门禁

1v1 RTC 发起必须校验：

1. 双方 `mutual`。
2. 任一方向未拉黑。

群 RTC 的成员选择规则由 `realtime-call` 继续定义，本设计只提供 1v1 用户关系门禁。

### KD-7：前端状态分层

推荐 Provider 分层：

```text
relationshipCapabilityProvider(userId)
greetingInboxProvider()
greetingOutboxProvider()
conversationCapabilityProvider(conversationId)
composerUiProvider(conversationId)
```

`ChatDetailPage` 不自行推导关注或拉黑状态。

## Metadata-first 落地顺序

1. `_shared/types.yaml` 删除旧关系枚举与字段，只保留 RelationshipState。
2. `user/follow_edge` 与 relationship capability 投影补齐能力位。
3. `user/block_edge` 补级联事件和服务语义。
4. `user/greeting_request` 补完整 API、事件、错误码与 storage 唯一索引。
5. `messages/conversation` 补 CreateConversation/SendMessage 关系门禁错误码和升级来源字段。
6. `rtc` 补 1v1 blocked/non-mutual 错误码。
7. codegen 后再改 Go service、Dart repository/provider/UI。

## 扩展场景映射

| 需求 | 扩展场景 |
|------|----------|
| 新增或补全 GreetingRequest | `S01` / `S03` |
| 扩展 Conversation 升级来源字段 | `S11` |
| 新增关系门禁错误码 | `S15` |
| 新增 UserBlocked/UserUnblocked/GreetingRequestReplied 事件 | `S06` |
| 新增关系能力投影 | `S07` |
| 增加门禁契约测试 | `S20` |

## 与下游特性的协作

### 对 `realtime-call`

- 1v1 入口与服务端发起均消费 `mutual + !blocked`。
- 文案与错误码不得再使用旧关系词。

### 对 `group-settings`

- 群设置页不提供拉黑群。
- 成员卡片和成员主页提供用户级拉黑。

### 对 `profile/chat`

- 主页消费关注状态动作矩阵。
- 请求箱和普通会话列表分层展示。
- blocked conversation 展示只读记录，不展示输入区和 1v1 RTC。

### 对 `intersection-unified-experience`

- 只消费关注边和共同关系事实，不新增关系名。
- 拉黑后被清理的关注边不得继续作为交集事实。

## 风险与预案

### 风险 1：跨存储一致性

BlockEdge、FollowEdge、GreetingRequest、Conversation 分属不同存储或服务，拉黑级联容易出现竞态。

**预案**：Block 写入必须发布事件；关注边清理和请求失效采用同步优先、事件补偿兜底；补偿任务可按 BlockEdge 反扫修复。

### 风险 2：服务端门禁遗漏

只隐藏端侧按钮会被 API 绕过。

**预案**：CreateConversation、SendMessage、RTC 发起各自补 T3 契约测试，断言非授权状态不落库。

### 风险 3：旧关系词回流

旧规格和 UI 常量中仍存在旧词。

**预案**：在 M0/M1 加静态扫描，禁止新增旧关系词作为关系等级；旧文档按本设计迁移。

## 适用场景与约束

- **适用**：关注、取消关注、拉黑、取消拉黑、打招呼、正式私信、1v1 RTC 门禁。
- **约束**：与 `user/follow_edge`、`user/block_edge`、`user/greeting_request`、`messages/conversation`、`rtc` metadata 一致。
- **局限性**：不覆盖群对象举报，不覆盖群组空间，不定义额外关系等级。
