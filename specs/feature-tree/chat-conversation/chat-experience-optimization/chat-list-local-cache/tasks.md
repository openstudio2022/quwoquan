# Tasks: chat-list-local-cache — 会话列表本地缓存

## Phase A — 缓存基础设施

- [ ] A1: 新建 `ConversationCacheEntry` 数据类 + Hive TypeAdapter（`lib/cloud/chat/cache/conversation_cache_entry.dart`）→ A9
- [ ] A2: 新建 `ConversationCacheService`（`lib/cloud/chat/cache/conversation_cache_service.dart`），Hive Box CRUD 封装 → A9
- [ ] A3: 在 `app_providers.dart` 注册 `conversationCacheServiceProvider`，App 启动时 `init()` → A9

## Phase B — 同步引擎

- [ ] B1: `ChatRepository` abstract 新增 `getConversationTimestamps()` 和 `batchGetConversations(ids)` 方法 → A2~A3
- [ ] B2: `MockChatRepository` 实现两个新方法（返回 mock 时间戳和数据）→ A2~A3
- [ ] B3: `RemoteChatRepository` 实现 `GET /conversations/timestamps` 和 `POST /conversations/batch` → A2~A3
- [ ] B4: 新建 `ConversationSyncService`（`lib/cloud/chat/cache/conversation_sync_service.dart`），实现全量索引比对 + 批量拉取逻辑 → A2~A5

## Phase C — UI 集成

- [ ] C1: 新建 `ConversationListNotifier` + `ConversationListState`，初始化读本地缓存，后台触发同步 → A1
- [ ] C2: `chat_page.dart` `_buildMessagesContent` 改造 — 替换 `FutureBuilder` 为 `ref.watch(conversationListProvider)` → A1
- [ ] C3: 新建会话本地优先逻辑 — 临时 ID 写缓存 + 异步云端同步 + 成功覆盖 → A6
- [ ] C4: 无网络降级 — 同步失败时静默忽略，本地数据继续有效 → A7

## Phase D — WebSocket 集成

- [ ] D1: 监听 `conv.updated` 事件，更新本地缓存对应条目 → A8

## Phase E — 测试

- [ ] E1: T2 — ConversationCacheService 单元测试（CRUD + 持久化）
- [ ] E2: T2 — ConversationSyncService 比对逻辑测试（新增/变化/删除）
- [ ] E3: T2 — 无白屏 Widget test（有缓存时直接渲染）
- [ ] E4: T1 — `/conversations/timestamps` 和 `/conversations/batch` 契约测试
- [ ] E5: `make gate`
