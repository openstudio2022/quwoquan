# 实时推送与离线同步 任务清单

> **顺序原则**：云侧事件接入（解除 P0 阻塞）→ 端侧 ChatMessageProvider 迁移 → WebSocket/Long-polling 状态机 → FCM/APNs → Gap fill → 集成测试

## 当前交付任务

### Phase 0：元数据与基础设施

- [ ] R0-1: [metadata] 更新 `service.yaml` 新增 `GET /v1/chat/inbox`、`POST /v1/chat/media/uploads:init`/`:complete`/`:abort` 路由
- [ ] R0-2: [metadata] 更新 `storage.yaml` messages 集合新增 TTL（14 天）
- [ ] R0-3: [codegen] `make verify-metadata && make codegen && make codegen-app`

### Phase 1：云侧事件接入 + Bug 修复（R-A1, R-A2）

- [ ] R1-1: [Red] 编写 EventPublisher 集成契约测试：SendMessage 后验证 Redis Pub/Sub 收到 MessageSent 事件
- [ ] R1-2: [Green] 重构 `MessageService` 构造函数，注入 `*mq.EventPublisher`
- [ ] R1-3: [Green] `SendMessage` 成功后发布 `MessageSent` 事件（异步，失败 log 不阻塞）
- [ ] R1-4: [Green] `RecallMessage` 后发布 `MessageRecalled` 事件
- [ ] R1-5: [Green] 重构 `MemberService` 注入 EventPublisher，`AddMembers`/`RemoveMember` 后发布 `MemberJoined`/`MemberLeft`
- [ ] R1-6: [Green] 重构 `ConversationService` 注入 EventPublisher，`UpdateSettings` 后发布 `ConversationSettingsUpdated`
- [ ] R1-7: [Green] `MarkAsRead` 后发布 `ReadReceiptSent`（仅 receiptEnabled 会话）
- [ ] R1-8: [Red] 编写 MarkAsRead UnreadCount 修复契约测试
- [ ] R1-9: [Green] 修复 `message_service.go` MarkAsRead：基于 `conv.MaxSeq - msg.Seq` 重算 UnreadCount
- [ ] R1-10: [Green] 更新 `main.go` 注入 EventPublisher 到所有服务 + InboxService 挂载到 ChatHandler
- [ ] R1-11: [Refactor] 验证所有事件 schema 与 events.yaml 一致

### Phase 2：ChatDetailPage 迁移到 ChatMessageProvider（R-A9, R-A10, R-A11）

- [ ] R2-1: [Red] 编写 ChatDetailPage Widget 测试：消息列表由 ChatMessageNotifier 驱动，发送后乐观插入
- [ ] R2-2: [Green] ChatDetailPage 移除 `_messages: List<Map<String, dynamic>>`，改用 `ref.watch(chatMessageProvider(conversationId))`
- [ ] R2-3: [Green] 发送消息改用 `chatMessageProvider.notifier.sendMessage()`
- [ ] R2-4: [Green] `chat_message_bubble.dart` 支持 `MessageDto` 输入（增加 `.fromDto()` 适配层或统一为 MessageDto）
- [ ] R2-5: [Green] 实现 seq gap 自动检测与修复（`syncFromSeq` 在检测到 gap 时触发）
- [ ] R2-6: [Green] 实现实时事件同步（撤回、回执、设置变更、成员变更→系统消息）
- [ ] R2-7: [Refactor] 助手会话适配（`_isAssistantConversation` 分支保持独立逻辑）

### Phase 3：RealtimeConnectionManager 自适应状态机（R-A3, R-A4, R-A5, R-A6, R-A7, R-A8）

- [ ] R3-1: [依赖] 添加 `web_socket_channel` 到 pubspec.yaml
- [ ] R3-2: [Red] 编写 RealtimeConnectionManager 状态机单元测试（三态切换）
- [ ] R3-3: [Green] 创建 `RealtimeConnectionManager` + 自适应传输状态机
- [ ] R3-4: [Green] 实现 `WebSocketTransport`（建连/心跳/断线检测/消息接收）
- [ ] R3-5: [Green] 实现 `LongPollTransport`（poll 发起/响应处理/自动重发）
- [ ] R3-6: [Green] 实现 `RealtimeConfig`（从 `/v1/config/realtime` 拉取配置 + 默认值兜底）
- [ ] R3-7: [Green] 实现 `ChatMessageHandler`（WebSocket 消息 → ChatMessageNotifier 路由）
- [ ] R3-8: [Green] 实现断线重连（指数退避 1s→30s + lastSeq gap fill）
- [ ] R3-9: [Green] 实现 WebSocket↔Long-polling 降级/升级切换
- [ ] R3-10: [Green] 注册 `realtimeManagerProvider` 和 `MockRealtimeConnectionManager` 到 `app_providers.dart`
- [ ] R3-11: [Green] ChatDetailPage 集成：进入页面触发 `onEnterChatDetail`，离开触发 `onLeaveChatDetail`
- [ ] R3-12: [Green] App lifecycle 集成：`WidgetsBindingObserver` 监听前后台切换
- [ ] R3-13: [Green] 连接状态 UI 指示（「连接中...」/「已连接」/「网络断开」）

### Phase 4：FCM/APNs 离线推送（R-A12, R-A13）

- [ ] R4-1: [依赖] 添加 `firebase_messaging` + `firebase_core` 到 pubspec.yaml
- [ ] R4-2: [配置] 添加 Firebase 项目配置（google-services.json / GoogleService-Info.plist）
- [ ] R4-3: [Red] 编写推送注册/注销 Widget 测试
- [ ] R4-4: [Green] 创建 `PushNotificationService`（权限请求/token 获取/token 上报/token 刷新）
- [ ] R4-5: [Green] 前台消息处理（静默更新 inbox 角标）
- [ ] R4-6: [Green] 通知点击处理（导航到 ChatDetailPage + 触发 后台→活跃 状态转换）
- [ ] R4-7: [Green] 免打扰过滤（`muted=true` 的会话静默处理，仅角标+1）
- [ ] R4-8: [Green] 用户退出登录时注销 push token

### Phase 5：集成测试与证据补齐（R-A14, R-A15）

- [ ] R5-1: [T3] 端云联调：EventPublisher → Redis → realtime-gateway（mock）→ 端侧 WebSocket 接收
- [ ] R5-2: [T3] 端云联调：Long-polling inbox 更新
- [ ] R5-3: [T3] 端云联调：Gap fill 断线后消息补全
- [ ] R5-4: [T4] 弱网测试：100kbps 下 WebSocket 断线→重连→gap fill
- [ ] R5-5: [T4] 旅程测试：App 后台→推送通知→点击→消息可见
- [ ] R5-6: [综合] 全量运行 `make gate-full`，确保无回归

## 搁置任务（带规划）

- [ ] S1: 国内厂商推送通道集成（小米/华为/OPPO/VIVO）（重启条件：国内 Android 推送到达率 <80%）
- [ ] S2: WebSocket 消息压缩 protobuf/msgpack（重启条件：WebSocket 带宽占比 >30%）
- [ ] S3: 端侧消息本地持久化 SQLite（重启条件：消息搜索特性启动）

## 未来演进任务

- [ ] E1: 连接迁移（节点下线无损漂移）
- [ ] E2: 多区域部署与就近接入
- [ ] E3: 端到端加密推送通道
- [ ] E4: 智能连接策略（根据电量/网络类型自动调整心跳间隔）
