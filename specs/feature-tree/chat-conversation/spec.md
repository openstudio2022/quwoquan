# L1 规格：聊天与会话 — 大群实时消息高并发重构

> **特性树路径**：`specs/feature-tree/chat-conversation/`（L1）
>
> **一句话定义（P1）**：面向趣聊 1v1 聊天与圈子群聊用户，解决大群写放大、消息乱序、实时推送缺失与离线同步空白四大问题，实现端到端可验收的 1v1 + 大群（上限 1,000 人）聊天能力。

对标飞书（10K 人群）、微信（500 人群）、Messenger，完成端到端可验收的 1v1 + 大群聊天建设。

## 0. 可量化验收标准（Top-3 摘要）

> 完整 25 条详见 `acceptance.yaml`。

| # | 可量化标准 | 验证方式 |
|---|-----------|---------|
| A14 | 消息 seq 严格递增，100 并发 seq 无间隔；clientMsgId 幂等（3 次 → DB 1 条）；2min 内撤回成功，超时拒绝 | T3-L2 契约测试 |
| A15 | SyncMessages(lastSeq=0) → 完整返回 500 条；lastSeq=250 → 后 250 条；lastSeq=500 → 空 | T3-L2 契约测试 |
| A21 | 1000 并发 SendMessage p99 <100ms；10K 消息 SyncMessages <3s；50 人 AddMembers <500ms | T3-L2 benchmark |

## 1. 背景

当前 chat-service 将成员列表嵌入 Conversation 文档，隐含 < 500 成员约束；Message 以 timestamp 排序，无服务端 seq，无法保证严格有序；会话状态（mute/pin/readCursor）混在 Conversation 文档中，写放大严重。实时推送依赖 SSE 单向通道，缺乏双向心跳与在线感知。

### 1.1 业界对标

| 能力 | 飞书 | 微信 | Messenger | 趣聊目标 |
|---|---|---|---|---|
| 群上限 | 10,000 | 500 | 250 | **1,000（可配置 max_group_size）** |
| 实时通道 | WebSocket | 私有 TCP | MQTT | **WebSocket（realtime-gateway）** |
| 消息有序性 | 服务端 seq | 服务端 seq | 服务端时间戳 | **服务端 seq（Redis INCR, per-conversation）** |
| 投递保障 | 至少一次 + 客户端去重 | 至少一次 | 至少一次 | **至少一次 + clientMsgId 幂等** |
| 离线同步 | seq gap 拉取 | sync-key 增量 | cursor 分页 | **seq gap 拉取（client last_seq → server delta）** |
| 已读回执 | 可配置 | 仅小群 | 全量 | **可配置（≤50 人群启用，>50 可关闭）** |
| 大群推送 | 仅在线 fanout | 仅在线 fanout | 仅在线 fanout | **仅在线 fanout + 离线拉取补偿** |
| 会话内 AI | 飞书 My AI（@提及） | — | Meta AI（@提及） | **小趣助手（@提及 / 邀请加入会话）** |

## 2. 目标用户

- 趣聊一对一聊天用户（日活主体）
- 圈子群聊成员（单群上限 1,000 人）
- 运营管理后台（消息审计、群管理）

## 3. 核心问题

1. **大群写放大**：嵌入成员 + 嵌入设置导致每条消息触发 Conversation 文档更新
2. **消息乱序**：无 seq，客户端依赖 timestamp 排序，时钟偏移导致乱序
3. **实时推送缺失**：SSE 单向，无心跳，无在线感知，大群无法精准推送
4. **离线同步空白**：无 seq gap 检测，重连后全量拉取
5. **端侧架构混杂**：`features/chat/` 与 `ui/chat/` 并存，状态管理未隔离

## 4. 功能范围

### 4.1 In-Scope（本次交付）

| 编号 | 功能 | 场景 |
|---|---|---|
| F1 | 1v1 聊天端到端 | 发送/接收/撤回/引用回复，文本+图片+视频+卡片 |
| F2 | 大群聊天端到端 | 最多 1,000 人群，消息严格有序，仅在线 fanout |
| F3 | 消息有序投递 | 服务端 seq + clientMsgId 幂等 + 客户端 gap 检测 |
| F4 | 实时推送 | WebSocket 首选 + long-polling 降级 + HTTP poll 兜底，三级传输 |
| F5 | 离线消息同步 | seq gap 拉取（client last_seq → server delta），支持批量补全 |
| F6 | 会话列表（Inbox） | 按最新消息时间排序，未读计数，置顶/免打扰 |
| F7 | 会话用户状态独立 | mute/pin/readCursor/unreadCount 独立存储，消除写放大 |
| F8 | 成员独立存储 | ConversationMember 独立 collection，支撑 1,000 成员 |
| F9 | 已读回执 | ≤50 人群默认开启，>50 可配置关闭 |
| F10 | 端侧 Domain 迁移 | `features/chat/` → `ui/chat/`，Provider 隔离 |
| F11 | 4 层测试覆盖 | L1 契约 + L2 集成 + L3 端侧 + L4 灰度 |
| F12 | 小趣助手会话内参与 | 邀请/移除助手 + @小趣触发 + 助手回复消息（memberType=assistant） |

### 4.2 Out-of-Scope（不在本次）

- 端到端加密（E2EE）
- 音视频通话
- 消息搜索（全文检索优化，后续独立特性）
- 消息热冷分离（归档策略，V2）
- 群公告 / 群文件 / 群应用
- 运营配置实时推送 V2（仅 topic 预留 + 骨架）

## 5. 业务对象模型（概要）

> 详细字段定义在 design 阶段更新 metadata YAML。

| 对象 | 职责 | 存储 | 变更点 |
|---|---|---|---|
| **Conversation** | 会话聚合根（轻量化） | MongoDB conversations | 移除 members/settings 嵌入，新增 maxSeq，去除 assistant 会话类型 |
| **Message** | 消息实体 | MongoDB messages | 新增 seq (per-conversation 单调递增) |
| **ConversationMember** | 成员关系 | MongoDB conversation_members（新） | 从嵌入拆出为独立 collection，新增 memberType（user/assistant） |
| **ConversationUserState** | 用户级会话状态 | MongoDB conversation_user_states（新） | mute/pin/readCursor/unreadCount 独立 |
| **ChatInbox** | 会话列表读模型 | MongoDB rm_chat_inbox | 改为 per-user 投影，source += MemberJoined |
| **MessageReceipt** | 消息回执 | MongoDB message_receipts（新，可选） | 仅 ≤50 人群启用 |

### 5.1 关键设计约束

- `Conversation.members` 字段废弃 → `ConversationMember` collection，索引 `{ conversationId, userId }` 唯一
- `ConversationType` 去除 `assistant`（底部导航栏已有独立助手入口），保留 `direct/group/circle/encrypted`
- 小趣助手通过 `ConversationMember(memberType=assistant)` 参与任意会话，@小趣 或显式邀请触发
- `Message.seq` 由 Redis `INCR conversation:{id}:seq` 原子生成，保证严格单调
- `ConversationUserState` 索引 `{ userId, conversationId }` 唯一，支撑 Inbox 查询
- 大群消息 fanout：Change Stream → realtime-gateway → 仅推送在线成员
- 离线成员重连时：client 上报 `last_seq` → 服务端返回 `[last_seq+1, maxSeq]` 区间消息

### 5.2 传输层决策：活跃度自适应传输

**消息发送方向**：始终通过 HTTP POST（可靠、有响应、有重试语义），不通过 WebSocket 发送。

**消息接收方向**：基于用户活跃度自适应切换（详见 realtime-gateway spec §4.0）：

| 用户状态 | 通道 | 延迟 | 服务端资源 |
|---|---|---|---|
| 活跃聊天中 | WebSocket | < 5ms | goroutine + fd |
| 在 App 中但未聊天 | Long-polling | ≤ `poll_interval_sec`（默认 60s） | **0**（HTTP 无状态） |
| App 后台 | APNs/FCM push | 秒级 | **0** |
| WebSocket 被拦截 | Long-polling（降级） | < 30s | **0** |
| 极端网络 | HTTP 轮询 SyncMessages | 5~30s | **0** |

**状态转换**：
- 进入聊天页 → 升级 WebSocket（实时消息流）
- 离开聊天页 / `ws_idle_timeout_sec`（默认 120s）无消息 → 回落 long-polling（inbox 角标 + 系统通知）
- App 后台 → 断开，仅 push 通知唤醒

**SSE 通道保留用途**：仅用于 AI Assistant 流式 token 输出（短命请求级连接），与聊天自适应传输独立共存。SSE/WebSocket/Long-polling 均由端侧主动发起连接，**不需要端侧暴露公网 IP**。

## 6. 性能目标

| 指标 | 1v1 | 大群（1,000 人） | 验证方式 |
|---|---|---|---|
| 消息发送 → 对端收到 p99 | < 200ms | < 500ms | L4 灰度实测 |
| 消息发送 API p99 | < 100ms | < 100ms | L2 契约测试 |
| 离线同步 10K 条 | — | < 3s | L2 基准测试 |
| 会话列表加载 p95 | < 150ms | — | L3 端侧测试 |
| WebSocket 重连成功率 | > 99.5% | > 99.5% | L4 灰度监控 |
| 消息零丢失 | seq gap = 0 | seq gap = 0 | L2 故障注入测试 |
| 消息去重率 | clientMsgId 100% 幂等 | clientMsgId 100% 幂等 | L2 契约测试 |
| Long-polling 降级后消息延迟 p95 | < 2s | < 5s | L2 + L4 |
| Transport 降级后消息零丢失 | seq gap = 0 | seq gap = 0 | L2 |

## 7. 约束

- 端侧数据源必须支持 mock/remote 无感切换（Provider 模式）
- 会话与消息接口统一 `{ items, nextCursor }` 分页协议
- 聊天全链路必须透传 `X-Request-Id` / `X-Trace-Id` / `X-Client-Page-Id` / `X-Client-Session-Id`
- realtime-gateway 为独立服务，chat-service 不直接管理 WebSocket 连接
- Message.seq 为服务端唯一真相，客户端禁止自行生成 seq
- 消息投递语义：至少一次（at-least-once），客户端通过 clientMsgId 去重
- 成员变更事件必须同步触发 ChatInbox 读模型更新
- 端侧 chat 页面必须在 `lib/ui/chat/` 下，禁止 `lib/features/chat/`

## 8. 适用范围与约束

### 8.1 适用场景

- 1v1 私聊 + 群聊（≤1,000 人）+ 圈子群聊
- 文本/图片/视频/卡片四种消息类型
- 单 App 内聊天场景（非跨 App 协议互通）
- 消息投递语义：至少一次（at-least-once），客户端通过 clientMsgId 去重

### 8.2 不适用场景

- 超过 1,000 人的超大群（需重新评估 fanout 策略）
- 端到端加密（E2EE），不在本次交付范围
- 音视频实时通话（独立特性域）
- 跨平台消息协议互通（如 Matrix/XMPP）
- 消息全文搜索（独立特性，需 Elasticsearch 等）

### 8.3 前置条件

- realtime-gateway 完成 WebSocket + Long-polling 服务实现（A1/A2/A14 的前置依赖）
- runtime-redis cluster 模式就绪（seq 分配 + 幂等去重的可靠性保障）
- user-service social graph 可用（联系人 ListContacts/SearchContacts 的数据源）

## 9. 验收重点（T1~T4 四层测试金字塔映射）

> 详细验收标准见 `acceptance.yaml`（A1~A25）。以下为各层验收重点概览。

### T1 契约与静态层（L1a + 静态校验）

| 维度 | 内容 |
|------|------|
| DTO 契约 | 6 个业务对象 DTO 全字段解析（常规/兼容/异常三维度） |
| 错误码契约 | 5 个 ChatErrorCode round-trip + fromCode + httpStatus + recoveryAction |
| Repository 契约 | 17 方法 Mock 实现与 Abstract 一致，返回结构与 service.yaml 对齐 |
| metadata 一致性 | fields.yaml → codegen → Go struct / Dart DTO 字段零偏差 |
| 目录迁移 | `lib/features/chat/` 清空，所有代码在 `lib/ui/chat/` 下 |

### T2 模块与交互层（L1b + 部分 L1c）

| 维度 | 内容 |
|------|------|
| ChatPage | 趣聊/同好 Tab 切换、会话列表加载、空态/错误态降级 |
| ChatDetailPage | 消息列表 seq 排序、发送乐观插入、撤回超时灰显 |
| ChatSettingsPage | 成员列表分页、mute/pin 切换、群名修改、错误态 |
| ChatMessageBubble | 文本/图片/Markdown/assistant_reply 四种气泡正确渲染 |
| 助手 UI | AssistantAnswerToolbar + ProcessDrawer + RegeneratePopup 交互 |
| mock/remote | ProviderScope 分别注入 Mock/Remote → 行为一致 |
| 已读回执 | ≤50 人群显示回执状态，>50 人群隐藏 |

### T3 端云集成层（L2 + L3）

| 维度 | 内容 |
|------|------|
| 会话 CRUD | MongoDB testcontainers 创建/查询/更新/删除 |
| 消息核心 | seq 分配 + clientMsgId 幂等 + 撤回时效 + 并发安全 |
| 离线同步 | SyncMessages lastSeq → delta 完整返回 |
| 成员管理 | 添加/移除 + 助手邀请/移除 + memberCount 维护 |
| 域事件 | 10 个事件 MessageSent/Recalled/MemberJoined 等 → EventSpy |
| ChatInbox | 未读计数 + lastMessageTime 排序 + mute/pin |
| 已读回执 | ≤50 人群写入/查询 + >50 关闭 |
| HTTP 契约 | 端侧 staging 17 API 三维度（协议/结构/语义） |
| 基准性能 | 1000 并发 p99 <100ms、10K 离线同步 <3s |

### T4 端到端旅程层（L1c 主旅程 + Patrol L4）

| 维度 | 内容 |
|------|------|
| 会话列表旅程 | 加载 → Tab 切换 → 进入详情（正常/空态/错误态） |
| 发消息旅程 | 输入 → 发送 → 乐观插入 → 服务端确认 → seq 排序 |
| 群管理旅程 | 创建群 → 邀请成员 → 设置 mute/pin |
| 助手旅程 | 邀请小趣 → @小趣 → 收到回复 → 反馈/重生成 |
| Patrol 真实设备 | IME 中文输入 + 系统通知点击 + 横竖屏稳定 |
| Patrol 实时投递 | 1v1 p99 <200ms + 大群 p99 <500ms |
| Patrol 自适应传输 | WS→long-poll→push→重连，seq gap=0 |

### 测试文件目录结构（规划）

```
test/
├── cloud/chat/
│   ├── contract/
│   │   ├── chat_repository_contract_test.dart        # T1: Repository 契约
│   │   └── chat_error_code_contract_test.dart        # T1: 错误码契约
│   ├── dto/contract/
│   │   ├── conversation_dto_contract_test.dart       # T1: DTO 契约
│   │   ├── message_dto_contract_test.dart            # T1: DTO 契约
│   │   ├── member_dto_contract_test.dart             # T1: DTO 契约
│   │   └── user_state_dto_contract_test.dart         # T1: DTO 契约
│   └── api_contract_runner.dart                      # T3: gamma HTTP 契约
├── ui/chat/
│   ├── widgets/
│   │   ├── chat_page_widget_test.dart                # T2: ChatPage 渲染
│   │   ├── chat_detail_page_widget_test.dart         # T2: ChatDetailPage 交互
│   │   ├── chat_settings_page_widget_test.dart       # T2: ChatSettingsPage 操作
│   │   ├── chat_message_bubble_widget_test.dart      # T2: 消息气泡类型
│   │   └── chat_assistant_ui_widget_test.dart        # T2: 助手 UI 组件
│   └── journeys/
│       ├── chat_conversation_list_journey_test.dart   # T4: 会话列表旅程
│       ├── chat_message_send_journey_test.dart        # T4: 发消息旅程
│       ├── chat_group_management_journey_test.dart    # T4: 群管理旅程
│       └── chat_assistant_journey_test.dart           # T4: 助手旅程
└── patrol/chat/
    ├── chat_realtime_delivery_test.dart               # T4: 实时投递 Patrol
    ├── chat_ime_input_test.dart                       # T4: 真实设备 Patrol
    └── chat_adaptive_transport_test.dart              # T4: 自适应传输 Patrol

# 云侧
services/chat-service/tests/
├── conversation_crud_contract_test.go                 # T3: 会话 CRUD
├── message_crud_contract_test.go                      # T3: 消息核心链路
├── message_sync_contract_test.go                      # T3: 离线同步
├── member_management_contract_test.go                 # T3: 成员管理
├── event_publish_contract_test.go                     # T3: 域事件发布
├── inbox_projection_contract_test.go                  # T3: ChatInbox 投影
├── conversation_settings_contract_test.go             # T3: 已读回执 + 设置
├── conversation_error_contract_test.go                # T3: 错误路径
├── conversation_compat_contract_test.go               # T3: 兼容性
└── benchmark_test.go                                  # T3: 基准性能
```

## 10. 跨特性依赖

| 依赖 | 特性节点 | 状态 |
|---|---|---|
| realtime-gateway（WebSocket 网关） | `gateway-orchestrator-foundation/realtime-gateway` | 本次新建 |
| circle-community 群聊绑定 | `circle-community` | 已有，需对齐 maxMembers |
| runtime-streaming（SSE + Change Stream） | `runtime/runtime-streaming` | 已有，需扩展 |
| notification-service（推送通道） | `notification` | 已有 |
