# Tasks: chat-list-local-cache — 会话列表本地缓存

## Phase A — 缓存基础设施

- [ ] A1: 新建 `ConversationCacheEntry` 数据类 + Hive TypeAdapter（`lib/cloud/chat/cache/conversation_cache_entry.dart`）→ A9
- [ ] A2: 新建 `ConversationCacheService`（`lib/cloud/chat/cache/conversation_cache_service.dart`），Hive Box CRUD 封装 → A9
- [ ] A3: 在 `app_providers.dart` 注册 `conversationCacheServiceProvider`，App 启动时 `init()` → A9

## Phase B — 同步引擎

- [ ] B1: `ChatRepository` abstract 新增 `getConversationTimestamps()` 和 `batchGetConversations(ids)` 方法 → A2~A3
- [ ] B2: `MockChatRepository` 实现两个新方法（返回 mock 时间戳和数据）→ A2~A3
- [ ] B3: `RemoteChatRepository` 实现 `GET /conversations/timestamps` 和 `POST /conversations/batch` → A2~A3
- [ ] B4: 新建 `ConversationSyncService`，实现分拆时间戳比对逻辑 → A2~A5
  - `settingsUpdatedAt` 变化 → 加入 needFetchIds 批量拉取
  - `lastMessageAt` 变化但 settingsUpdatedAt 未变 → 仅更新 lastMessagePreview/lastMessageAt/unreadCount
- [ ] B5: 同步防抖 — 30 秒最小间隔，防止切 Tab 频繁触发 → KD-9

## Phase C — UI 集成

- [ ] C1: 新建 `ConversationListNotifier` + `ConversationListState`，初始化读本地缓存，后台触发同步 → A1
- [ ] C2: `chat_page.dart` `_buildMessagesContent` 改造 — 替换 `FutureBuilder` 为 `ref.watch(conversationListProvider)` → A1
- [ ] C3: 新建会话本地优先逻辑 — 临时 ID 写缓存 + 异步云端同步 + 成功覆盖 → A6
- [ ] C4: 无网络降级 — 同步失败时静默忽略，本地数据继续有效 → A7

## Phase D — 消息时间全链路

- [ ] D1: 新建 `ChatTimeFormatter` 工具类 → KD-7
  - `formatBubbleTime(DateTime serverTime)` — 气泡展示时间（上午/下午 H:mm）
  - `formatListTime(DateTime serverTime)` — 列表展示时间（今天/昨天/周X/M-d）
  - `tryParseServerTime(String? iso)` — 解析云端 ISO 8601 UTC+8，失败返回 null 不回退本地时钟
- [ ] D2: `MessageDto.toDisplayMap` 改造 — 使用 `ChatTimeFormatter.formatBubbleTime` 替代手写时间格式化
- [ ] D3: `MessageDto.fromMap` 修复 — timestamp 解析失败时不再回退 `DateTime.now()`
- [ ] D4: `ChatMessageNotifier.sendMessage` 改造 — 乐观阶段不赋本地时间，展示"发送中"状态
- [ ] D5: `chat_page.dart` 列表时间改造 — `lastMessageTime` 用 `ChatTimeFormatter.formatListTime` 展示
- [ ] D6: `chat_detail_page.dart` 中 `_submitChatInput` 改造 — 不再用 `DateTime.now()` 生成展示时间

## Phase E — WebSocket 事件驱动

- [ ] E1: `RealtimeMessageHandler` — `MessageSent` 新增更新 conversationCache 的 lastMessage/unreadCount → A8, KD-10
- [ ] E2: `RealtimeMessageHandler` — 实现 `ConversationSettingsUpdated` handler → KD-10
- [ ] E3: `RealtimeMessageHandler` — 实现 `MemberJoined`/`MemberLeft` handler（系统消息 + 成员数更新）→ KD-10
- [ ] E4: WS 重连后自动 `syncFromSeq` 补全 seq gap → KD-11

## Phase F — 测试

- [ ] F1: T2 — ConversationCacheService 单元测试（CRUD + 持久化）
- [ ] F2: T2 — ConversationSyncService 分拆比对逻辑测试（新增/变化/删除 + settingsUpdatedAt vs lastMessageAt）
- [ ] F3: T2 — 无白屏 Widget test（有缓存时直接渲染）
- [ ] F4: T1 — `/conversations/timestamps` 和 `/conversations/batch` 契约测试
- [ ] F5: T2 — ChatTimeFormatter 多时区单元测试（UTC+8/UTC-4/UTC+0/无时区回退）
- [ ] F6: T2 — 同步防抖单元测试（30s 内不重复同步）
- [ ] F7: T2/T3 — WS 重连 seq gap 补全测试
- [ ] F8: `make gate`
