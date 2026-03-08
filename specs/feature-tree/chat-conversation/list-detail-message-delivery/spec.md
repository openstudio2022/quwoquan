# L2 规格：消息投递与列表 — 高并发大群消息有序投递

> 覆盖 1v1 和大群（≤1,000 人）场景的消息发送、接收、排序、离线同步、已读回执全链路。

## 1. 功能说明

消息投递是聊天核心链路，本特性承载从发送到展示的完整路径：

```
客户端发送 → chat-service 持久化 + seq 分配 → 域事件发布
  → realtime-gateway fanout（在线推送）
  → 客户端 WebSocket 接收 → seq 排序展示
  → 离线用户重连 → seq gap 拉取 → 补全展示
```

### 1.1 关键链路

| 链路 | 1v1 | 大群 (≤1,000) | 说明 |
|---|---|---|---|
| **发送** | **HTTP POST** | **HTTP POST** | **始终 HTTP，不走 WebSocket** |
| 实时推送（活跃态） | WebSocket | WebSocket (仅在线活跃) | 用户在聊天页时 realtime-gateway fanout |
| 通知推送（空闲态） | Long-polling | Long-polling | 用户在 App 但未聊天，收 inbox 角标 |
| 离线唤醒（后台态） | APNs/FCM push | APNs/FCM push | App 后台，push 通知唤醒 |
| 兜底同步 | HTTP 轮询 SyncMessages | HTTP 轮询 | 极端网络，定时轮询 |
| 离线补全 | seq gap pull | seq gap pull | client lastSeq → server delta |
| 排序 | by seq | by seq | 严格单调递增 |
| 去重 | clientMsgId | clientMsgId | 服务端幂等 |
| 已读回执 | 默认开启 | ≤50 人开启，可配置 | 写入 message_receipts |

**为什么发送走 HTTP 而非 WebSocket**：HTTP POST 有明确的请求-响应语义（成功返回 messageId + seq），天然支持重试和超时控制。WebSocket send 无内置 ACK 机制，丢包后无法确认。飞书/Discord/Slack 均采用相同设计：HTTP 发送 + WebSocket/长轮询 接收。

**自适应传输核心逻辑**（详见 realtime-gateway spec §4.0）：
- 用户在聊天页 + 消息活跃 → WebSocket（延迟 < 5ms）
- 用户在 App 但不在聊天页 → Long-polling（间隔 `poll_interval_sec` 默认 60s，服务端零资源）
- App 后台 → 断开，仅 APNs/FCM
- WebSocket 升级被代理拦截 → 停留在 Long-polling（自动重试升级）

## 2. 业务对象变更（概要）

### 2.1 Message 新增字段

| 字段 | 类型 | 说明 |
|---|---|---|
| `seq` | int64 | per-conversation 单调递增，Redis INCR 生成 |
| `clientMsgId` | string | 客户端生成的 UUID，用于幂等去重 |

### 2.2 新增实体：ConversationUserState

| 字段 | 类型 | 说明 |
|---|---|---|
| `userId` | string | 用户 ID |
| `conversationId` | ObjectId | 会话 ID |
| `readSeq` | int64 | 用户已读到的 seq |
| `unreadCount` | int | 未读消息数 |
| `muted` | bool | 免打扰 |
| `pinned` | bool | 置顶 |
| `lastReadAt` | timestamp | 最后已读时间 |

唯一索引：`{ userId, conversationId }`

### 2.3 新增实体：MessageReceipt（可选，仅 ≤50 人群）

| 字段 | 类型 | 说明 |
|---|---|---|
| `messageId` | ObjectId | 消息 ID |
| `userId` | string | 已读用户 |
| `readAt` | timestamp | 已读时间 |

### 2.4 ChatInbox 读模型升级

- 改为 per-user 投影（当前是全局投影，不正确）
- source_events 新增 `MemberJoined`、`MemberLeft`、`ConversationSettingsUpdated`
- 新增 `lastSeq` 字段用于 gap 检测

## 3. API 变更（概要）

### 3.1 新增 API

| 方法 | 路径 | 操作 | 说明 |
|---|---|---|---|
| POST | /v1/chat/conversations/{id}/sync | SyncMessages | 上报 lastSeq，返回 gap 消息 |
| POST | /v1/chat/conversations/{id}/messages/{msgId}/read | MarkAsRead | 标记已读（更新 readSeq） |
| GET | /v1/chat/conversations/{id}/messages/{msgId}/receipts | GetReceipts | 获取消息回执列表 |

### 3.2 变更 API

| 操作 | 变更 |
|---|---|
| SendMessage | 请求增加 `clientMsgId`，响应增加 `seq` |
| ListMessages | 支持 `afterSeq` / `beforeSeq` 参数 |
| ListConversations | 响应增加 `maxSeq`（会话最大 seq） |

## 4. 消息投递流程

### 4.1 发送流程

```
1. 客户端 POST /messages { type, content, clientMsgId }
2. chat-service:
   a. clientMsgId 幂等检查（Redis SET NX, TTL 5min）
   b. Redis INCR conversation:{id}:seq → 获取 seq
   c. 持久化 Message { ..., seq, clientMsgId }
   d. 更新 Conversation.maxSeq + lastMessage*
   e. 发布域事件 MessageSent { conversationId, messageId, seq, ... }
3. 返回 { messageId, seq, timestamp }
```

### 4.2 实时推送流程

```
1. MessageSent → Redis Pub/Sub channel: rt:conversation:{id}
2. realtime-gateway 每个节点消费 Redis Pub/Sub
3. 查找订阅 conversation/{id} topic 的在线连接
4. 逐连接 WebSocket write { type: "message", topic, payload, seq }
5. 未在线用户 → notification-service 触发离线推送
```

### 4.3 离线同步流程

```
1. 客户端重连 WebSocket，发送 { type: "subscribe", topic: "conversation/{id}", lastSeq: 100 }
2. realtime-gateway 转发给 chat-service: SyncMessages(conversationId, lastSeq=100)
3. chat-service 查询 messages WHERE conversationId=X AND seq > 100 ORDER BY seq ASC LIMIT 500
4. 返回 gap 消息列表 + hasMore
5. 客户端逐页拉取直到 gap 填满
```

## 5. 约束

- Message.seq 由服务端 Redis INCR 原子生成，客户端禁止自行分配
- clientMsgId 幂等窗口 5 分钟（Redis SET NX + TTL）
- 大群消息仅推送在线成员，离线成员重连后拉取
- 已读回执仅在 `receiptEnabled` 为 true 的会话中写入 message_receipts
- 已读回执阈值默认 50 人，可通过会话级 settings 覆盖
- 离线同步单次返回最多 500 条，客户端分页拉取
- 端侧消息列表必须按 seq 排序，禁止按 timestamp 排序

## 6. 验收标准

| 编号 | 条件 | 场景 | 验证层 |
|---|---|---|---|
| M-A1 | SendMessage 返回 seq，seq 严格递增 | 并发 100 条 | L2 |
| M-A2 | clientMsgId 幂等：重复 3 次只存 1 条 | 网络重试 | L2 |
| M-A3 | 1v1 消息 WebSocket 推送 < 200ms p99 | 在线投递 | L2+L4 |
| M-A4 | 1000 人群 WebSocket 推送 < 500ms p99 | 大群投递 | L2+L4 |
| M-A5 | 离线 500 条同步 < 3s | gap pull | L2 |
| M-A6 | 消息按 seq 排序展示，乱序到达仍正确 | 端侧排序 | L3 |
| M-A7 | 已读回执 10 人群显示，100 人群不显示 | 阈值控制 | L2+L3 |
| M-A8 | 端云 metadata 字段一致 | codegen | L1 |
| M-A9 | ListMessages 支持 afterSeq/beforeSeq 分页 | 历史消息 | L2 |
| M-A10 | ConversationUserState 正确维护 unreadCount | 未读计数 | L2 |
