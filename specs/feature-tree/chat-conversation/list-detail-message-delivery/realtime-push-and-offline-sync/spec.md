# 实时推送与离线同步（Realtime Push & Offline Sync）

> **层级**：L3_subfeature（隶属 L2 `list-detail-message-delivery`，L1 `chat-conversation`）
> **状态**：specified
> **依赖**：`gateway-orchestrator-foundation/realtime-gateway`（服务端 WebSocket 网关）、`chat-service`（消息持久化 + 域事件发布）

## 背景与动机

趣聊聊天当前的消息接收链路仅依赖 HTTP 轮询（`SyncMessages`，间隔 ≥5s），导致：

- **延迟高**：接收方感知延迟 ≥5s，远超微信 ≤300ms 的商用基线
- **实时感缺失**：ChatDetailPage 未接入 `ChatMessageProvider`，消息展示依赖手动 `listMessages` 拉取，无乐观更新、无 seq gap 修复
- **无离线推送**：App 退到后台后无 APNs/FCM 推送，用户完全不知道有新消息
- **EventPublisher 未接入**：`chat-service` 中 `EventPublisher` 已创建但未在 `SendMessage` 后发布域事件，下游 realtime-gateway 无事件可消费
- **能耗浪费**：轮询模式持续消耗端侧电量和服务端带宽

`realtime-gateway` 已完成独立 L2 规格（含 WebSocket/Long-polling/自适应传输设计），但**端侧集成**和**云侧事件接入**尚未实施。本特性补齐从域事件发布 → 实时推送 → 端侧接收 → 离线推送 → 断线恢复的完整闭环。

## 目标用户

- **趣聊所有聊天用户**：需要实时收到新消息的 1v1 和群聊用户
- **后台用户**：App 在后台时仍需收到新消息通知的用户

## 功能范围

### F1 云侧事件接入（chat-service → realtime-gateway）

1. **EventPublisher 接入 SendMessage**：`chat-service` 的 `message_service.go` 在 SendMessage 成功后调用 `EventPublisher.Publish(MessageSent)`，发布到 Redis Pub/Sub `rt:conversation:{conversationId}`
2. **EventPublisher 接入其他域事件**：`MessageRecalled`、`MemberJoined`、`MemberLeft`、`ConversationSettingsUpdated`、`ReadReceiptSent` 均发布到对应 realtime channel
3. **事件幂等**：每个事件携带 `eventId`（UUID），realtime-gateway 去重

### F2 端侧自适应传输状态机（RealtimeConnectionManager）

4. **传输状态机实现**：实现 `Long-polling(空闲) ↔ WebSocket(活跃) ↔ Disconnected(后台)` 三态切换
5. **状态转换触发**：
   - 空闲→活跃：进入 ChatDetailPage / 发送消息 / 10s 内收到 ≥3 条消息
   - 活跃→空闲：离开 ChatDetailPage / 120s 无消息收发
   - 任意→后台：App 进入后台（iOS ~3s / Android ~30s）
   - 后台→空闲：App 回到前台
   - 后台→活跃：点击消息推送通知直接进入聊天页
6. **配置拉取**：App 启动时从 `/v1/config/realtime` 获取自适应参数（`ws_idle_timeout_sec`、`poll_interval_sec`、`ws_heartbeat_sec` 等），支持运营热更新
7. **Mock/Remote 双模式**：`MockRealtimeConnectionManager`（本地事件模拟）+ `RemoteRealtimeConnectionManager`（真实 WebSocket/Long-polling），通过 `appDataSourceModeProvider` 切换

### F3 WebSocket 活跃态

8. **WebSocket 建连**：`wss://{gateway}/v1/realtime/ws?token={jwt}&topics=conversation/{id},inbox/{userId}`
9. **心跳**：30s ping/pong，90s 无 pong 判定断线
10. **消息接收**：收到 `{ type: "message", topic, payload, seq }` → 路由到 `ChatMessageHandler` → 更新 `ChatMessageNotifier` 消息列表
11. **断线重连**：指数退避（1s→2s→4s→8s→16s→max 30s），重连时携带 `lastSeq` 做 gap fill
12. **Token 刷新**：收到 `auth_expired` 帧 → 刷新 JWT → 重连

### F4 Long-polling 空闲态

13. **Long-polling 发起**：`GET /v1/realtime/poll?topics=inbox,system&lastSeq={maxInboxSeq}&timeout=60`
14. **响应处理**：有新消息 → 立即返回 → 更新 inbox 角标 → 立即发起下一次 poll；超时 → 204 → 立即重新 poll
15. **空闲态仅订阅 inbox + system**：不订阅具体 conversation topic（节省服务端资源）

### F5 ChatDetailPage 实时集成

16. **ChatDetailPage 接入 ChatMessageProvider**：消息列表由 `ChatMessageNotifier` 驱动，支持乐观更新、seq 排序、gap 检测
17. **乐观发送**：发送消息后立即插入本地列表（status=sending），服务端确认后更新 status=sent 并填入 seq
18. **实时消息插入**：WebSocket 收到新消息 → `ChatMessageNotifier.addMessage()` → 列表实时更新（无需手动刷新）
19. **Seq gap 修复**：检测到 seq 不连续 → 自动调用 `SyncMessages` 补全缺失消息
20. **状态同步**：ReadReceipt/Recall/SettingsUpdate 等事件实时同步到 UI

### F6 离线推送（APNs/FCM）

21. **FCM 集成（Android）**：`firebase_messaging` 包集成，App 启动注册 FCM token，上报到 user-service
22. **APNs 集成（iOS）**：通过 `firebase_messaging` 统一处理（Firebase 代理 APNs），App 启动注册 token
23. **Token 管理**：token 变更时上报服务端；用户退出登录时注销 token
24. **推送触发**：realtime-gateway 判定用户所有设备均 disconnected → 通知 notification-service → 发送 push
25. **推送内容**：`{ title: "发送者名称", body: "消息预览（截断50字）", data: { conversationId, messageId } }`
26. **推送点击处理**：点击推送通知 → App 唤醒/回到前台 → 直接导航到对应 ChatDetailPage → 触发 后台→活跃 状态转换 → WebSocket 建连 + gap fill
27. **免打扰**：`ConversationUserState.muted=true` 的会话不发送推送（服务端过滤）

### F7 断线恢复与一致性

28. **状态转换 gap fill**：每次从 后台→空闲 或 后台→活跃 时，自动对所有有未读的会话执行 `SyncMessages`
29. **WebSocket→Long-polling 降级**：WebSocket 建连失败 → 停留在 Long-polling → 60s 后重试 WebSocket Upgrade
30. **Long-polling 失败降级**：Long-polling 失败 → 降级为定时 `SyncMessages` 轮询（间隔 5~30s，指数退避）
31. **消息零丢失保证**：任何传输状态切换过程中，通过 seq gap fill 确保消息不丢失

## 不做什么（Out of Scope）

- **realtime-gateway 服务端实现**：属于独立 L2（`gateway-orchestrator-foundation/realtime-gateway`），本特性仅做端侧集成和云侧事件接入
- **notification-service 实现**：离线推送的服务端调度属于独立特性，本特性仅完成端侧 FCM/APNs 注册和推送处理
- **消息压缩（protobuf/msgpack）**：V2 优化
- **连接迁移（节点下线无损漂移）**：V2 优化
- **多区域部署与就近接入**：V2 优化
- **端到端加密推送**：E2EE 独立特性
- **富媒体推送（图片/视频预览）**：推送通知仅含文字预览

## 约束

### 技术约束

- WebSocket 客户端必须使用 `web_socket_channel` 包（Flutter 官方推荐）
- 所有实时连接必须通过 `RealtimeConnectionManager` 管理，禁止 UI 层直接创建 WebSocket
- 推送 token 管理必须通过 `firebase_messaging`，禁止直接调用平台原生 API
- `ChatDetailPage` 必须切换到 `ChatMessageProvider` 驱动，禁止继续使用本地 `_messages` 状态
- `EventPublisher` 必须在 `SendMessage` 事务成功后发布，禁止在事务外发布导致不一致
- 端侧 Provider 注册在 `app_providers.dart`，禁止 UI 直接实例化

### 业务约束

| 指标 | 要求 |
|------|------|
| 消息端到端延迟（WebSocket 活跃态） | ≤300ms p99（1v1）、≤500ms p99（1000人群） |
| 消息端到端延迟（Long-polling 空闲态） | ≤60s（等效轮询间隔） |
| Inbox 角标更新延迟 | ≤5s（Long-polling 态） |
| 离线推送延迟（App 后台） | ≤10s（含服务端判定 + FCM/APNs 投递） |
| 推送点击到消息可见 | ≤3s（含 App 唤醒 + WebSocket 建连 + gap fill） |
| 断线重连成功率 | ≥99.5%（30s 内） |

### 弱网与可靠性约束

| 场景 | 行为 |
|------|------|
| WebSocket 建连失败 | 停留 Long-polling，60s 后重试 Upgrade |
| WebSocket 断线（弱网） | 指数退避重连（1s~30s），重连后 gap fill |
| Long-polling 超时 | 立即重新发起 |
| Long-polling 失败 | 降级为 SyncMessages 定时轮询（5~30s） |
| App 后台 >24h | 回到前台后 gap fill 所有有未读的会话 |
| 推送 token 过期 | 自动刷新并上报 |

### 并发性能约束

| 指标 | 要求 |
|------|------|
| 单用户 WebSocket 连接数 | ≤5（多设备） |
| 单节点 WebSocket 容量 | 50K 活跃连接 |
| Gap fill 批量大小 | ≤500 条/次 |
| Inbox 更新频率 | ≤1 次/s（合并多次变更） |

### 部署约束

- realtime-gateway 独立部署（`deploy/service/realtime-gateway/`），不与 chat-service 混部
- 端侧 FCM/APNs 需配置 Firebase 项目（`google-services.json` / `GoogleService-Info.plist`）
- 灰度策略：integration 全量 → prod 10% → 50% → 100%
- 回滚条件：WebSocket 连接成功率 <95% 或消息丢失率 >0.1% 或推送送达率 <90%

### 实时性约束

| 指标 | Phase 1（本次） | Phase 2（优化） |
|------|----------------|----------------|
| 1v1 消息延迟（活跃态） | ≤300ms p99 | ≤200ms p99 |
| 群消息延迟（≤1000人，活跃态） | ≤500ms p99 | ≤300ms p99 |
| Inbox 角标延迟（空闲态） | ≤60s | ≤30s |
| 离线推送延迟 | ≤10s | ≤5s |
| 断线→恢复全量同步 | ≤5s | ≤3s |

## 适用范围

- **适用场景**：趣聊 1v1 私聊和群聊的实时消息接收、后台推送、断线恢复
- **前置条件**：`realtime-gateway` 服务端已部署（或 Mock 模式开发），`chat-service` EventPublisher 已创建
- **不适用**：AI 助手流式输出（使用 SSE，与自适应传输独立共存）、实时音视频通话（使用 WebRTC + LiveKit SFU）

## 对标输入与吸收结论

| 对标 | 借鉴点 | 不借鉴点 | 适用边界 |
|------|--------|---------|---------|
| **微信** | 消息延迟 ≤300ms；后台推送必达；静默推送（免打扰会话仅角标）；推送点击直达聊天页 | 自研协议栈（MMTLS）过于复杂；微信的专有推送通道（不走 FCM/APNs） | 延迟和推送体验直接对标 |
| **飞书** | HTTP POST 发送 + WebSocket 接收分离架构；多设备同步；Token 过期自动续期 | 过重的企业特性（审批/多租户） | 架构模式直接借鉴 |
| **Discord** | WebSocket 事件驱动；心跳机制（Opcode 1/11）；断线恢复携带 session_id 和 seq | Resume 机制依赖 Discord 特有的 session 缓存 | 心跳和断线恢复参考 |
| **Telegram** | 差分同步（pts/qts/seq）；多 DC 路由；即时推送 | 自研 MTProto 协议过于复杂 | 差分同步理念参考，实现简化 |

## 子节点结构

| L4 Story | 职责 | 交付边界 |
|---------|------|---------|
| `websocket-push-gap-fill-policy` | WebSocket 推送接收 + seq gap fill 策略 + 断线恢复 | F2(4-7) + F3(8-12) + F5(16-20) + F7(28-31) |

## 跨特性依赖

| 依赖 | 方向 | 说明 |
|------|------|------|
| `gateway-orchestrator-foundation/realtime-gateway` | ← | 服务端 WebSocket 网关（V1 同步开发） |
| `unified-entry-security` | ← | JWT 鉴权方案（WebSocket + HTTP），chat-service 需从信任 `X-Client-User-Id` 升级为 gateway 层 JWT 校验 |
| `notification-service` | → | 离线推送调度（本特性做端侧集成，服务端调度由 notification-service 负责） |
| `voice-message` | ← | 语音消息已验证的乐观发送 + 离线队列模式，本特性复用其模式 |
| `rich-media-message` | ← | 媒体消息的实时接收展示（视频/文件/图片气泡需在实时推送到达后正确渲染） |

## 验收重点

### T1 契约与静态层

- EventPublisher 接入后事件 schema 与 metadata events.yaml 一致
- RealtimeConnectionManager Provider 注册正确
- FCM/APNs 配置文件存在且格式正确

### T2 模块与交互层

- 传输状态机三态切换正确（Mock 模式下）
- ChatDetailPage 接入 ChatMessageProvider 后消息实时更新
- 推送通知点击导航正确

### T3 端云集成层

- WebSocket 建连→订阅→收消息端云联调
- Long-polling 发起→收 inbox 更新端云联调
- Gap fill 断线后消息补全联调
- EventPublisher → Redis → realtime-gateway → 端侧完整链路

### T4 端到端旅程层

- 1v1 发送→WebSocket 推送→接收方气泡出现旅程（≤300ms）
- App 后台→推送通知→点击→消息可见旅程
- 弱网断线→重连→gap fill→消息补全旅程
- 多设备同时在线消息同步旅程

详细验收标准见 `acceptance.yaml`。
