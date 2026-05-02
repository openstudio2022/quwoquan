# chat-conversation 设计方案

## 设计动因

当前 chat metadata 存在 3 个核心结构缺陷：
1. **成员嵌入**：`Conversation.members/memberIds` 嵌入文档，16MB 文档限制 → 1,000 人群不可行
2. **设置耦合**：`Conversation.settings`（mute/pin/readCursor）嵌入，每个用户操作触发整个文档更新 → 写放大
3. **无序投递**：`Message` 无 `seq` 字段，依赖 `timestamp` 排序，时钟偏移导致乱序

此外，`ConversationType` 移除 `assistant`（底部导航栏已有独立助手入口），小趣助手改为通过
`ConversationMember(memberType=assistant)` 参与任意会话（@提及或邀请触发），对标飞书 My AI 和 Meta AI。

云侧 `chat-service` 尚未实现（无 Go 代码），本次设计即首次全量实现。

## 上游输入评审

- L1 spec.md：稳定，6 个核心对象模型已明确，12 项功能（F1~F12）+ 11 条性能目标 + §8 适用范围与约束 + §9 T1~T4 验收映射
- acceptance.yaml：升级为标准 `level_acceptance` 格式，A1~A25 共 25 条可测量验收标准（T1×6 + T2×7 + T3×10 + T4×4，覆盖 spec 全部功能与性能）
- 依赖 realtime-gateway（已 design）和 runtime-redis（已 design）
- metadata：8 个 YAML 文件全部完整（aggregate/fields/storage/events/service/errors/projections/tests），与 KD-1~KD-10 对齐
- 无阻断项

## 对标输入分析

| 对标 | 借鉴 | 不借鉴 | 适用边界 |
|---|---|---|---|
| 飞书 | 成员外置 + per-conversation seq + 离线 seq gap pull | 10K 群成员（我们上限 1K） | 大群消息有序投递 |
| 微信 | sync-key 增量同步 + 服务端 seq | 私有协议 | 离线同步策略 |
| Discord | channel 独立消息流 + 仅在线推送 | 复杂的 guild/channel/thread 三层结构 | 大群 fanout |
| Messenger | clientMsgId 幂等 + 乐观发送 | MQTT 传输（我们用 WebSocket） | 客户端去重 |

## 方案对比

### 方案 A：成员+设置外置 + seq 有序 + 独立 ConversationUserState（选定）

- `ConversationMember` 独立 collection（索引 `{conversationId, userId}` 唯一）
- `ConversationUserState` 独立 collection（per-user per-conversation，索引 `{userId, conversationId}` 唯一）
- `Message` 新增 `seq`（Redis INCR）+ `clientMsgId`（UUID 幂等）
- `Conversation` 轻量化：移除 `members/memberIds/settings`，新增 `maxSeq/memberCount`
- `ChatInbox` 改为由 `ConversationUserState` 驱动，新增 `lastSeq`

**优点**：
- 成员数无文档限制，1,000 人群无压力
- 用户状态写入不触发 Conversation 文档更新，消除写放大
- seq 保证严格有序，客户端排序零歧义
- clientMsgId 幂等 5min 窗口，网络抖动无重复
- 与 realtime-gateway fanout 完美匹配（seq → gap fill）

**缺点**：
- 数据模型变更大（新增 3 个 collection + 修改 2 个），migration 工作量高
- 记录数据迁移需要脚本（members 嵌入 → ConversationMember + memberIds 废弃）
- seq 依赖 Redis INCR，Redis 故障影响消息发送

**适用条件**：群成员 > 100，消息量 > 1K/天/群

### 方案 B：保持嵌入，加 seq 字段（不选）

在现有嵌入结构上仅新增 `Message.seq`，不拆分成员和设置。

**优点**：改动最小
**缺点**：
- 1,000 人群仍受 16MB 文档限制（~500 成员已接近）
- 设置写放大仍存在
- 无法独立查询某用户的未读状态

## 选型决策

**选定方案 A**：全面外置 + seq 有序。

理由：这是首次实现 chat-service，没有记录债务压力，直接按正确架构构建。
嵌入方案在 1,000 人群场景下存在硬限制，不值得为"改动小"而留债。

## 关键设计决策

### KD-1：Conversation 轻量化

移除嵌入字段，新增运行时统计字段：

| 废弃字段 | 替代 |
|---|---|
| `memberIds []string` | `ConversationMember` collection + `Conversation.memberCount` |
| `members []ConversationMember` | `ConversationMember` collection |
| `settings ConversationSettings` | `ConversationUserState` collection |
| `assistantSkillId` | `ConversationMember.assistantSkillId`（仅 memberType=assistant） |

新增字段：

| 字段 | 类型 | 说明 |
|---|---|---|
| `maxSeq` | int64 | 当前会话最大 seq（冗余，加速 gap 判定） |
| `memberCount` | int | 当前成员数（冗余，避免 count 查询） |
| `maxGroupSize` | int | 群上限（默认 1000，可配置） |
| `receiptEnabled` | bool | 是否启用已读回执（≤50 人默认 true） |

### KD-2：ConversationMember 独立 collection

```yaml
collection: conversation_members
unique_index: { conversationId: 1, userId: 1 }
fields: [_id, conversationId, userId, memberType, displayName, avatarUrl, role, assistantSkillId, joinedAt, invitedBy]
```

查询模式：
- "某会话的所有成员"：by `conversationId`（分页）
- "某用户参与的所有会话"：by `userId`（Inbox 关联）
- "某用户在某会话的角色"：by `{conversationId, userId}`（权限检查）
- "某会话是否有助手"：by `{conversationId, memberType: assistant}`

### KD-3：ConversationUserState 独立 collection

```yaml
collection: conversation_user_states
unique_index: { userId: 1, conversationId: 1 }
fields: [_id, userId, conversationId, readSeq, unreadCount, muted, pinned, lastReadAt, updatedAt]
```

写入场景（均不触发 Conversation 文档更新）：
- 用户读消息 → 更新 `readSeq` + `unreadCount`
- 用户设置免打扰 → 更新 `muted`
- 用户置顶 → 更新 `pinned`
- 新消息到达 → 更新 `unreadCount`（批量 `$inc`）

### KD-4：Message.seq 生成

```
Redis INCR seq:conversation:{conversationId} → seq
```

- per-conversation 隔离，互不干扰
- 严格单调递增（Redis 单线程保证）
- 写入 Message 后同步更新 `Conversation.maxSeq`
- Redis key 使用 `realtime` scene（runtime-redis 路由）

### KD-5：clientMsgId 幂等

```
Redis SET NX dedup:{conversationId}:{clientMsgId} → 1, TTL 300s
```

- 300s 内重复提交直接返回已有 messageId + seq
- 超过 300s 后相同 clientMsgId 视为新消息（极端场景，用户已知）
- Redis key 使用 `realtime` scene

### KD-6：ChatInbox 读模型升级

从全局投影改为 per-user 投影，由 `ConversationUserState` 驱动：

```yaml
source_events:
  - MessageSent           # 更新 lastMessage* + unreadCount
  - MemberJoined          # 创建 inbox 条目
  - MemberLeft            # 删除 inbox 条目
  - ConversationSettingsUpdated  # 更新 muted/pinned
```

新增字段：`lastSeq`（会话最新 seq，端侧 gap 检测用）

### KD-7：chat-service 目录结构

```
services/chat-service/
├── cmd/api/main.go
├── internal/
│   ├── domain/
│   │   ├── conversation.go             # Conversation entity
│   │   ├── conversation_repository.go  # Repository interface
│   │   ├── conversation_events.go      # Domain events
│   │   ├── message.go                  # Message entity
│   │   ├── message_repository.go       # Repository interface
│   │   ├── member.go                   # ConversationMember entity
│   │   ├── member_repository.go        # Repository interface
│   │   ├── user_state.go               # ConversationUserState entity
│   │   ├── user_state_repository.go    # Repository interface
│   │   ├── receipt.go                  # MessageReceipt entity（可选）
│   │   └── receipt_repository.go       # Repository interface
│   ├── application/
│   │   ├── conversation_service.go     # 会话 CRUD + 成员管理
│   │   ├── message_service.go          # 消息发送 + seq + 幂等 + 撤回
│   │   ├── inbox_service.go            # Inbox 查询 + 未读计数
│   │   └── sync_service.go             # 离线同步 SyncMessages
│   ├── adapters/
│   │   ├── http/
│   │   │   ├── conversation_handler.go
│   │   │   ├── message_handler.go
│   │   │   └── sync_handler.go
│   │   └── mq/
│   │       └── event_publisher.go      # 域事件 → Redis Pub/Sub + EventStore
│   └── infrastructure/
│       ├── persistence/
│       │   ├── conversation_mongo_repo.go
│       │   ├── message_mongo_repo.go
│       │   ├── member_mongo_repo.go
│       │   ├── user_state_mongo_repo.go
│       │   └── receipt_mongo_repo.go
│       ├── cache/
│       │   └── conversation_cache.go
│       └── migration/
│           └── 001_chat_collections.up.js
├── configs/config.yaml
├── go.mod
└── Makefile
```

### KD-8：端侧 ChatRepository 扩展

现有 `ChatRepository` 接口仅有 `listConversations` 和 `listMessages`，需扩展：

```dart
abstract class ChatRepository {
  // 已有
  Future<PaginatedResponse<ConversationDto>> listConversations({...});
  Future<PaginatedResponse<MessageDto>> listMessages(String conversationId, {...});
  
  // 新增
  Future<SendMessageResponse> sendMessage(String conversationId, SendMessageRequest req);
  Future<void> recallMessage(String conversationId, String messageId);
  Future<SyncResponse> syncMessages(String conversationId, {required int lastSeq});
  Future<void> markAsRead(String conversationId, String messageId);
  Future<List<ReceiptDto>> getReceipts(String conversationId, String messageId);
  Future<void> updateSettings(String conversationId, ConversationSettingsDto settings);
  Future<ConversationDto> createConversation(CreateConversationRequest req);
  Future<void> addMembers(String conversationId, List<String> userIds);
  Future<void> removeMember(String conversationId, String userId);
}
```

### KD-9：消息发送走 HTTP POST 的端侧实现

```dart
// 端侧发送消息流程
1. 生成 clientMsgId (UUID)
2. 乐观插入本地消息列表（status=sending, seq=null）
3. HTTP POST /messages { type, content, clientMsgId }
4. 成功 → 更新本地消息（status=sent, seq=response.seq, messageId=response.id）
5. 失败 → 重试（携带相同 clientMsgId，服务端幂等）
6. 按 seq 排序展示（seq=null 的发送中消息排最后）
```

### KD-10：小趣助手会话内参与

**模型变更**：
- `ConversationType` 移除 `assistant`，保留 `direct/group/circle/encrypted`
- `ConversationMember` 新增 `memberType`（`user`/`assistant`）+ `assistantSkillId`
- `Conversation.assistantSkillId` 废弃，改由 `ConversationMember.assistantSkillId` 承载

**交互流程**：
```
1. 用户在聊天中点击"邀请小趣" → POST /conversations/{id}/assistant { skillId? }
2. 创建 ConversationMember { memberType: assistant, role: member, userId: "assistant:{skillId}" }
3. 发布 AssistantInvited 事件 → realtime-gateway 通知会话成员
4. 用户在消息中 @小趣 → chat-service 检测 mentions 含 assistant memberId
   → 发布 AssistantMentioned 事件 → assistant-service 消费
5. assistant-service 处理后通过 SendMessage API 回复（senderId=assistant:{skillId}, type=assistant_reply）
6. 移除助手 → DELETE /conversations/{id}/assistant → 删除 assistant member
```

**约束**：
- 每个会话最多 1 个助手成员（409 Conflict）
- 助手消息 `type=assistant_reply`，端侧使用特殊气泡样式
- 助手成员 `role` 固定为 `member`，无管理权限
- 助手不计入 `maxGroupSize` 上限

### KD-11：Runtime 统一集成（补充决策）

当前 main.go 直接 import MongoDB/Redis 驱动，违反 `01-arch-constraints §1.3~§1.4`。需重构为标准启动模板：

```go
func main() {
    cfg := config.MustLoad("configs/config.yaml")
    shutdown := observability.MustInit(cfg)
    defer shutdown()
    reg := registry.MustLoad(cfg.MetadataDir)
    repos := repository.MustInitFromRegistry(reg, cfg)
    handler := http.NewServer(cfg, reg, repos)
    http.ListenAndServe(handler, cfg)
}
```

| 能力 | 当前状态 | 目标状态 |
|------|---------|---------|
| HTTP 服务 | `net/http.Server` | `runtime/http.NewServer` + observability 中间件 |
| 配置读取 | `os.Getenv` + 自定义 `loadConfig` | `runtime/config.RuntimeConfigProvider` |
| 可观测 | 无 | `runtime/observability`（日志/指标/追踪） |
| 消息发布 | 无 | `runtime/messaging.MessageEnvelope` |
| 实体注册 | 无 | `runtime/registry.EntityRegistry` |

### KD-12：部署架构

```
                    ┌─── dev 环境 ──────────────────────┐
                    │  chat-service (独立进程)           │
                    │  realtime-gateway (独立进程)       │
                    └───────────────────────────────────┘
                    ┌─── integration / prod 环境 ───────┐
                    │  seed-box (合并进程)               │
                    │    └─ domains: [content, chat,     │
                    │       user, circle, assistant,     │
                    │       integration, gateway,        │
                    │       orchestrator]                │
                    └───────────────────────────────────┘
```

**部署产物**：

| 产物 | 路径 | 说明 |
|------|------|------|
| chat-service Dockerfile | `deploy/service/chat-service/Dockerfile` | dev 独立部署 |
| seed-box Dockerfile | `deploy/service/seed-box/Dockerfile`（已有） | integration/prod 合并部署 |
| k8s base | `deploy/service/chat-service/kustomize/base/` | deployment + service |
| k8s overlays | `deploy/service/chat-service/kustomize/overlays/{dev,integration,prod}/` | 环境差异化 |
| process_domain_mapping | `deploy/shared/process_domain_mapping.yaml`（已有） | 已包含 chat 域映射 |

**灰度发布策略**：

1. **integration 部署**：chat 域纳入 seed-box → `make deploy-integration` → 运行 L3 API 契约测试
2. **prod 灰度（10%）**：canary deployment → 监控 p99/错误率/seq gap 24h
3. **prod 全量（100%）**：确认监控指标正常 → 全量切流
4. **回滚预案**：chat 域从 seed-box 摘除 → 端侧降级为 mock 数据源

### KD-13：门禁集成

chat-service 需完整纳入 `make gate` 流水线：

| 门禁 | 命令 | 说明 |
|------|------|------|
| chat-service build | `go build ./services/chat-service/...` | 编译检查 |
| chat-service L2 | `go test ./services/chat-service/... -count=1` | 云侧契约测试 |
| chat L1 | `flutter test test/cloud/chat/ test/ui/chat/` | 端侧 T1+T2+T4(L1c) |
| chat L3 | `make test-api-contract-chat` | gamma HTTP 契约 |
| chat L4 | `patrol test test/patrol/chat/` | Patrol 真实设备 |

**需新增**：

- `services/chat-service/Makefile`（build / test / gate targets）
- 根 `Makefile` 的 `gate` target 加入 chat-service
- `.github/workflows/` 中 CI 配置覆盖 chat-service

### KD-14：适用场景与约束

**适用**：1v1 + ≤1000 人群，文本/图片/视频/卡片，at-least-once 投递 + clientMsgId 去重。

**不适用**：超大群（>1000）、E2EE、音视频、跨平台协议、全文搜索。

**当前方案与目标最优方案的差距**：
- 当前无 realtime-gateway → 无实时推送（A1/A2/A14 依赖）
- 当前无 inbox 投影 → 会话列表无未读计数（A18 依赖）
- 当前端侧无 codegen DTO → Map<String,dynamic> 直传（A4 依赖）

**演进路径**：Phase 0~3 可独立交付 HTTP CRUD 全链路；Phase 4（realtime-gateway）并行推进；Phase 5 灰度部署验收。

## Story 与测试层映射（T1~T4 治理视图）

| Story | 内容 | T1 | T2 | T3 | T4 | 验收项 |
|-------|------|:--:|:--:|:--:|:--:|--------|
| S1 | metadata + codegen（DTO 契约 + 错误码） | ● | | | | A1~A5 |
| S2 | ChatPage/Detail/Settings Widget 渲染 | | ● | | | A6~A8 |
| S3 | ChatMessageBubble + 助手 UI | | ● | | | A9~A10 |
| S4 | mock/remote 切换 + 已读回执 UI | ● | ● | | | A11~A12 |
| S5 | 云侧 Conversation CRUD 契约 | | | ● | | A13 |
| S6 | 消息 seq + 幂等 + 撤回 | | | ● | | A14 |
| S7 | 离线同步 SyncMessages | | | ● | | A15 |
| S8 | 成员管理 + 助手 | | | ● | | A16 |
| S9 | 域事件发布（10 事件） | | | ● | | A17 |
| S10 | ChatInbox 投影 + 未读计数 | | | ● | | A18 |
| S11 | 已读回执云侧 + 设置 | | | ● | | A19 |
| S12 | 端侧 gamma HTTP 契约 | | | ● | | A20 |
| S13 | 基准性能测试 | | | ● | | A21 |
| S14 | L1c Journey（会话列表/发消息/群管理） | | | | ● | A22~A24 |
| S15 | L4 Patrol（真实设备 + 灰度性能） | | | | ● | A25 |
| S16 | runtime 集成 + Makefile + 门禁 | ● | | ● | | A4(gate) |
| S17 | 部署 + 灰度 + 生产 | | | ● | ● | A25 |

## 未来演进

- **消息热冷分离**：触发单会话消息 > 100 万条时，冷消息归档到低成本存储
- **端到端加密（E2EE）**：触发合规要求或用户需求
- **消息全文搜索优化**：触发搜索请求量 > 1K/天
- **群公告 / 群文件 / 群应用**：触发产品需求

## 存量带规划任务

- 记录数据迁移脚本（members 嵌入 → ConversationMember）— 当前无记录数据，首次实现无需迁移
- assistant 类型会话与 PA 系统的深度集成
