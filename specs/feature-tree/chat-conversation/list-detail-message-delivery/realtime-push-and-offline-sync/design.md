# 实时推送与离线同步 设计方案

## 设计动因

spec.md 指出当前消息接收仅靠 HTTP 轮询（≥5s 延迟），EventPublisher 已创建但未接入 SendMessage，ChatDetailPage 未使用 ChatMessageProvider，无 FCM/APNs 离线推送。本设计解决从域事件发布到端侧实时接收、离线推送、断线恢复的完整闭环。

## 上游输入评审

- **spec.md**：功能范围清晰（F1~F7，31 功能点），约束完备
- **acceptance.yaml**：R-A1~R-A15 可测量，test_layers 已映射
- **realtime-gateway spec+design**：服务端 WebSocket 网关方案已冻结（独立 Go 服务 + goroutine-per-conn + Redis Pub/Sub + 自适应传输）
- **阻断项**：realtime-gateway 服务端需与本特性并行开发；本设计聚焦云侧事件接入 + 端侧集成
- **MarkAsRead Bug**：`message_service.go` 第 200-203 行 UnreadCount 计算 bug 需在本次修复

## 对标输入分析

| 对标 | 借鉴点 | 不借鉴点 | 当前差距 | 收敛路径 |
|------|--------|---------|---------|---------|
| 微信 | 消息 ≤300ms；后台推送必达；贴耳切听筒 | 自研 MMTLS 协议栈 | 无实时通道，≥5s 延迟 | 本次实现 WebSocket + FCM/APNs |
| 飞书 | HTTP 发送 + WebSocket 接收分离 | 企业多租户 | 同架构但未实现 WebSocket 端 | 本次接入 |
| Discord | 心跳 Opcode + Resume 机制 | 桌面端重连逻辑 | 无心跳和 resume | 本次实现 |

## 方案对比

### 方案对比 1：云侧事件发布模式

#### 方案 A：应用层注入 EventPublisher（选定）

将 `EventPublisher` 注入 `MessageService`/`MemberService`/`ConversationService`，在操作成功后同步发布事件。

**优点**：事件与业务操作在同一执行流程，事务语义清晰；EventPublisher 代码已就绪；延迟最低（无额外异步链路）
**缺点**：Redis Pub/Sub 故障会影响主请求（需捕获错误但不 block 返回）
**适用条件**：事件发布延迟要求极低（<5ms）

#### 方案 B：MongoDB Change Stream 驱动

利用 `storage.yaml` 已定义的 `messages` change_stream，由独立 consumer 监听 insert 事件后发布到 Redis。

**优点**：业务逻辑与事件发布完全解耦；不影响主请求延迟
**缺点**：额外延迟（Change Stream 传播 10~50ms）；需维护独立 consumer 进程；与 realtime-gateway 的 Redis Pub/Sub 路径重复（gateway 也会消费 change stream）
**适用条件**：可接受更高延迟的场景

**选定方案 A**。理由：EventPublisher 已就绪，延迟最低，实现最简。Redis 发布失败时 log + 不阻塞返回（消息已持久化，接收方可通过 SyncMessages 补齐）。

### 方案对比 2：ChatDetailPage 消息状态管理

#### 方案 A：ChatMessageProvider 全面接管（选定）

将 `ChatDetailPage` 的 `_messages: List<Map<String, dynamic>>` 替换为 `ChatMessageNotifier`（已有代码），通过 `ref.watch(chatMessageProvider(conversationId))` 驱动 UI。

**优点**：乐观更新、seq 排序、gap 检测、重试逻辑已在 ChatMessageNotifier 中实现；类型安全（`MessageDto` vs `Map<String, dynamic>`）；与 WebSocket 实时消息推送的对接点天然存在（`addMessage`）
**缺点**：需迁移 ChatDetailPage 中所有 `_messages` 引用；助手会话逻辑需适配
**适用条件**：需要实时更新的消息列表

#### 方案 B：保持本地状态 + 添加 Sync 层

在现有 `_messages` 基础上，添加一个 SyncLayer 定期拉取新消息并 merge。

**优点**：改动最小
**缺点**：两套状态管理并存，维护复杂；无法实现乐观更新；类型不安全；与 WebSocket 推送对接困难
**适用条件**：仅做轻量改进

**选定方案 A**。理由：ChatMessageNotifier 已有完整实现（loadMessages/sendMessage/retrySendMessage/recallMessage/syncFromSeq），仅需在 ChatDetailPage 中切换数据源。

### 方案对比 3：离线推送 SDK

#### 方案 A：firebase_messaging 统一 SDK（选定）

使用 `firebase_messaging` 同时处理 Android FCM 和 iOS APNs（Firebase 代理 APNs token 转换）。

**优点**：单一 SDK 覆盖双端；Firebase 自动处理 APNs token 转换；社区成熟
**缺点**：依赖 Google 服务；中国大陆 Android 需考虑 FCM 可达性
**适用条件**：有 Firebase 基础设施

#### 方案 B：分端原生实现

iOS 用 `flutter_apns`，Android 用各厂商推送 SDK（小米/华为/OPPO/VIVO）。

**优点**：国内 Android 推送到达率更高
**缺点**：维护成本高（4~5 个 SDK）；集成复杂度高
**适用条件**：国内 Android 用户为主

**选定方案 A**。理由：Phase 1 先用 Firebase 统一方案验证链路，Phase 2 按需接入国内厂商推送通道。

## 选型决策

| 决策 | 选定 | 理由 |
|------|------|------|
| 云侧事件发布 | 应用层注入 EventPublisher | 延迟最低，代码已就绪 |
| 端侧消息状态 | ChatMessageProvider 全面接管 | 已有完整实现，类型安全 |
| WebSocket 客户端 | `web_socket_channel` | Flutter 官方推荐，已稳定 |
| 离线推送 | `firebase_messaging` | 单一 SDK 覆盖双端 |
| 状态机 | Riverpod StateNotifier | 与现有 Provider 模式一致 |

## 关键设计决策

### KD-1: EventPublisher 注入模式（已定）

```go
// message_service.go — 注入 EventPublisher
type MessageService struct {
    repo      persistence.ChatRepository
    cache     *cache.ConversationCache
    publisher *mq.EventPublisher     // ← 新增
}

func (s *MessageService) SendMessage(ctx context.Context, req SendMessageRequest) (*model.Message, error) {
    // ... 幂等检查 + seq 分配 + 持久化 ...
    msg, err := s.persistMessage(ctx, req)
    if err != nil { return nil, err }

    // 事件发布（失败不阻塞返回）
    go func() {
        _ = s.publisher.Publish(context.Background(), mq.DomainEvent{
            Type:           event.MessageSent,
            ConversationID: req.ConversationId,
            ActorID:        req.SenderId,
            Payload: map[string]any{
                "messageId": msg.ID, "seq": msg.Seq,
                "type": msg.Type, "content": msg.Content,
                "mediaUrl": msg.MediaUrl, "media": msg.Media,
            },
        })
    }()
    return msg, nil
}
```

所有域事件（MessageRecalled/MemberJoined/MemberLeft/ConversationSettingsUpdated/ReadReceiptSent）同理注入。

### KD-2: MarkAsRead Bug 修复（已定）

```go
// 修复前（bug）：seqDiff 永远为 0
state.ReadSeq = msg.Seq
seqDiff := int(msg.Seq - state.ReadSeq) // 永远 0

// 修复后：基于 maxSeq 重算
conv, _ := s.repo.FindConversationByID(ctx, req.ConversationId)
state.ReadSeq = msg.Seq
state.UnreadCount = int(conv.MaxSeq - msg.Seq)
if state.UnreadCount < 0 { state.UnreadCount = 0 }
```

### KD-3: main.go 依赖注入重构（已定）

```go
// 修复前：eventPublisher 和 inboxSvc 被 _ 忽略
eventPublisher := mq.NewEventPublisher(router.Scene("realtime"))
_ = eventPublisher

// 修复后：注入到所有服务
eventPublisher := mq.NewEventPublisher(router.Scene("realtime"))
messageSvc := application.NewMessageService(chatStore, convCache, eventPublisher)
memberSvc := application.NewMemberService(chatStore, convCache, eventPublisher)
conversationSvc := application.NewConversationService(chatStore, convCache, eventPublisher)
handler := httpadapter.NewChatHandler(conversationSvc, messageSvc, memberSvc, inboxSvc)
```

### KD-4: RealtimeConnectionManager 自适应状态机（已定）

```
lib/cloud/services/realtime/
├── realtime_connection_manager.dart   # 状态机 + Provider
├── realtime_message_handler.dart      # Topic → Handler 路由
├── realtime_config.dart               # 配置（从 /v1/config/realtime 拉取）
├── transport/
│   ├── websocket_transport.dart       # WebSocket 实现
│   └── longpoll_transport.dart        # Long-polling 实现
└── mock/
    └── mock_realtime_manager.dart     # Mock 模式（本地事件模拟）
```

状态机核心逻辑：
```dart
enum TransportState { idle, active, disconnected }

class RealtimeConnectionManager extends StateNotifier<TransportState> {
    // idle: Long-polling（inbox + system topic）
    // active: WebSocket（conversation + inbox + system topic）
    // disconnected: 无连接（App 后台）

    void onEnterChatDetail(String conversationId) {
        // idle → active: 建立 WebSocket + 订阅 conversation topic
    }
    void onLeaveChatDetail() {
        // active → idle (after ws_idle_timeout_sec): 关闭 WebSocket → Long-polling
    }
    void onAppBackground() {
        // any → disconnected: 关闭所有连接
    }
    void onAppForeground() {
        // disconnected → idle: 启动 Long-polling + gap fill
    }
}
```

### KD-5: ChatDetailPage 迁移到 ChatMessageProvider（已定）

迁移清单：
1. 移除 `_messages: List<Map<String, dynamic>>`，替换为 `ref.watch(chatMessageProvider(conversationId))`
2. 移除 `_loadMessages()` 手动加载，由 `ChatMessageNotifier.loadMessages()` 驱动
3. 发送消息改为 `ref.read(chatMessageProvider(conversationId).notifier).sendMessage(...)`
4. 消息列表 Widget 改为消费 `ChatMessageState.messages`（`List<MessageDto>`）
5. `chat_message_bubble.dart` 需同步支持 `MessageDto` 输入（当前基于 `Map<String, dynamic>`）
6. 助手会话保持现有逻辑（`_isAssistantConversation` 分支不变）

### KD-6: WebSocket 消息接收集成（已定）

```dart
class ChatMessageHandler implements RealtimeMessageHandler {
    final Ref ref;

    void onMessage(String topic, Map<String, dynamic> payload) {
        // topic: "conversation/{conversationId}"
        final conversationId = extractConversationId(topic);
        final eventType = payload['type'] as String;

        switch (eventType) {
            case 'MessageSent':
                final msg = MessageDto.fromMap(payload['payload']);
                ref.read(chatMessageProvider(conversationId).notifier)
                    .addMessage(msg);
            case 'MessageRecalled':
                ref.read(chatMessageProvider(conversationId).notifier)
                    .recallMessage(payload['payload']['messageId']);
            case 'ReadReceiptSent':
                // 更新回执状态
            case 'MemberJoined':
            case 'MemberLeft':
                // 插入系统消息
        }
    }
}
```

### KD-7: FCM/APNs 集成模式（已定）

```dart
class PushNotificationService {
    Future<void> init() async {
        // 1. 请求推送权限
        await FirebaseMessaging.instance.requestPermission();
        // 2. 获取 token 并上报
        final token = await FirebaseMessaging.instance.getToken();
        await userRepository.registerPushToken(token!);
        // 3. 监听 token 刷新
        FirebaseMessaging.instance.onTokenRefresh.listen((token) {
            userRepository.registerPushToken(token);
        });
        // 4. 前台消息处理（静默更新 inbox 角标）
        FirebaseMessaging.onMessage.listen(_handleForegroundMessage);
        // 5. 通知点击处理（导航到 ChatDetailPage）
        FirebaseMessaging.onMessageOpenedApp.listen(_handleNotificationTap);
    }
}
```

### KD-8: 消息 TTL 14 天（已定）

MongoDB messages 集合添加 TTL 索引：
```yaml
# storage.yaml 新增
ttl:
  field: timestamp
  expire_after_seconds: 1209600  # 14 天
```

媒体文件 CDN URL 使用 signed URL（TTL 同步 14 天），过期后不可访问。

### KD-9: InboxService HTTP 暴露（已定）

```go
// chat_handler.go 新增
func (h *ChatHandler) handleListInbox(w http.ResponseWriter, r *http.Request) {
    userId := resolveUserID(r)
    cursor := r.URL.Query().Get("cursor")
    limit := parseIntOrDefault(r.URL.Query().Get("limit"), 50)
    inbox, err := h.inboxService.ListUserInbox(ctx, userId, cursor, limit)
    // ...
}
```

路由：`GET /v1/chat/inbox?cursor=X&limit=50`，返回 per-user inbox 投影。

### KD-10: 聊天媒体上传路由（chat-service 自建）（已定）

```go
// chat_handler.go 新增
func (h *ChatHandler) handleInitChatUpload(w http.ResponseWriter, r *http.Request)     { /* MediaStore.InitUpload */ }
func (h *ChatHandler) handleCompleteChatUpload(w http.ResponseWriter, r *http.Request) { /* MediaStore.CompleteUpload */ }
func (h *ChatHandler) handleAbortChatUpload(w http.ResponseWriter, r *http.Request)    { /* MediaStore.AbortUpload */ }
```

路由注册在 chat-service：`POST /v1/chat/media/uploads:init`、`POST /v1/chat/media/uploads:complete`、`POST /v1/chat/media/uploads:abort`。
底层调用 `runtime/media.MediaStore`，复用 OSS presign + CDN 生成逻辑。

## TDD / ATDD 策略

1. **R-A1~R-A2 先行**：先写云侧事件发布契约测试（EventPublisher spy 验证 Publish 调用）
2. **R-A9 TDD**：先写 ChatDetailPage → ChatMessageProvider 集成测试（mock repo），验证消息列表由 Notifier 驱动
3. **R-A5~R-A7**：WebSocket 建连/心跳/重连测试用 mock WebSocket server
4. **R-A12~R-A13**：FCM/APNs 测试用 mock firebase_messaging

## Story 与测试层映射

| 任务组 | T1 契约 | T2 模块 | T3 集成 | T4 旅程 |
|--------|---------|---------|---------|---------|
| 云侧事件接入 | EventPublisher 契约 | — | EventPublisher→Redis 联调 | — |
| MarkAsRead 修复 | UnreadCount 重算契约 | — | MarkAsRead API 联调 | — |
| ChatDetailPage 迁移 | — | ChatMessageProvider Widget | ChatDetailPage+Repo 联调 | 消息列表实时更新 |
| WebSocket 活跃态 | — | 状态机 Widget | WebSocket 端云联调 | 发送→推送→展示 |
| Long-polling 空闲态 | — | Long-poll Widget | Long-poll 端云联调 | Inbox 角标更新 |
| FCM/APNs | — | 推送注册 Widget | 推送端云联调 | 后台推送→点击→消息 |
| Gap fill | — | Gap 检测 Widget | SyncMessages 联调 | 断线→恢复→补全 |

## 实时性与弱网设计

| 场景 | 策略 |
|------|------|
| WebSocket 活跃态 | 消息延迟 ≤300ms p99（1v1）/ ≤500ms p99（1000人群） |
| Long-polling 空闲态 | Inbox 角标延迟 ≤60s |
| WebSocket 断线 | 指数退避 1s→30s，重连后 gap fill |
| WebSocket 升级失败 | 停留 Long-polling，60s 后重试 |
| Long-polling 失败 | 降级为 SyncMessages 轮询 5~30s |
| App 后台 | 断开连接，仅 FCM/APNs |
| App 回前台 | Long-polling + 全量 gap fill |
| 弱网（100kbps） | WebSocket 保持但消息合并（写缓冲背压） |
| 极弱网/断网 | 断开 → 本地缓存 → 恢复后 gap fill |

## 并发性能与容量设计

| 指标 | 设计值 |
|------|--------|
| 单用户 WebSocket 连接 | ≤5（多设备） |
| 单节点 WebSocket | 50K（realtime-gateway） |
| Gap fill 批量 | ≤500 条/次 |
| Inbox Long-poll | 60s hold，有消息立即返回 |
| 事件发布 QPS | ≥10K/s（Redis PUBLISH） |

## 灰度发布与回滚设计

- **Phase 1**: integration 全量（R-A1~R-A14 全部 implemented）
- **Phase 2**: prod 10%，24h 监控 WebSocket 连接成功率 ≥95%、消息丢失率 <0.1%、推送送达率 ≥90%
- **Phase 3**: prod 50%，同上
- **Phase 4**: prod 100%
- **回滚条件**：连接成功率 <90% 或消息丢失率 >0.5% 自动回滚

## 未来演进

| 演进项 | 触发条件 |
|--------|---------|
| 国内厂商推送通道（小米/华为/OPPO/VIVO） | 国内 Android 推送到达率 <80% |
| 消息压缩（protobuf/msgpack） | WebSocket 带宽占比过高 |
| 连接迁移（节点下线无损漂移） | 部署频率提升导致连接频繁断开 |
| 端侧消息本地持久化（SQLite） | 消息搜索特性启动 |
| 消息已读状态跨设备同步 | 多设备用户增长 |
