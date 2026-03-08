# L2 规格：realtime-gateway — 统一实时通信网关

> 独立 WebSocket 网关服务，承载趣聊消息推送、外部渠道同步、运营配置下发等所有实时通信场景。

## 1. 背景

当前实时推送依赖 `runtime/streaming` 的 SSE 通道，单向且无状态，无法满足：
- 大群消息双向低延迟投递
- 客户端在线感知与精准推送
- 外部渠道（飞书等）云端接入并转发至 App
- 运营配置实时下发

飞书/Discord/Slack 均采用独立 WebSocket 网关架构，与业务服务解耦，独立水平扩展。

## 2. 定位

realtime-gateway 是**平台级基础设施服务**，不属于任何业务域，为所有需要实时推送的服务提供统一长连接管理和消息路由。

### 2.1 与现有组件关系

| 组件 | 职责 | 关系 |
|---|---|---|
| chat-service | 消息持久化、seq 分配、域事件发布 | realtime-gateway 的上游事件源 |
| runtime/streaming (SSE) | Assistant 流式输出 | 保留，SSE 仅用于 AI 流式场景 |
| runtime/eventstore | 域事件持久化 | 事件最终一致性保障 |
| notification-service | 离线推送（APNs/FCM） | realtime-gateway 判定用户离线后通知 notification |

## 3. 功能范围

### 3.1 V1 交付（本次）

| 编号 | 功能 | 说明 |
|---|---|---|
| G1 | WebSocket 连接管理 | 建连/鉴权/心跳/断线检测/优雅关闭 |
| G2 | Topic 订阅路由 | 客户端订阅 topic（conversation/{id}、inbox、system），服务端按 topic 推送 |
| G3 | 消息 fanout | 消费 chat-service 域事件（Redis Pub/Sub），推送至在线成员 |
| G4 | 在线感知 | 维护用户在线状态（userId → connId 映射），支持精准推送与离线判定 |
| G5 | 断线重连协议 | 客户端重连时携带 lastEventId/lastSeq，服务端判定是否需要 gap fill |
| G6 | 跨节点广播 | 多实例部署时通过 Redis Pub/Sub 跨节点路由消息 |
| G7 | 外部渠道 Adapter SPI | 飞书 Webhook → realtime-gateway → topic 路由 → 端侧消费 |
| G8 | 运营配置 topic（骨架） | 预留 `system/config` topic，客户端注册 handler，V2 实现推送逻辑 |
| G9 | 可观测性 | 连接数/消息吞吐/延迟 Prometheus 指标 + 结构化日志 |

| G10 | 传输层自动降级 | WebSocket → long-polling → HTTP poll 三级降级 |
| G11 | 连接资源管理 | per-node 上限 + per-user 多设备限制 + 优雅拒绝 |
| G12 | 写缓冲区背压 | WebSocket 写入慢时 → 跳过旧消息 / 合并推送 / 断开 |

### 3.2 V2 留待后续

- 运营配置推送完整实现（feature flag / UI 配置 / 策略热更新）
- 消息压缩（protobuf / msgpack）
- 连接迁移（节点下线时连接无损漂移）
- 多区域部署与就近接入

## 4. 核心设计约束

### 4.0 活跃度自适应传输（Adaptive Transport）

不同于传统"WebSocket 失败才降级"的模式，realtime-gateway 采用**基于用户活跃度的自适应传输**：
WebSocket 仅在用户活跃聊天时建立，空闲时自动回落到 long-polling，后台时断开仅靠 push 通知。

**传输状态机**：

```
                ┌──────────────────────────────────┐
                │           App 启动                │
                └───────────────┬──────────────────┘
                                │
                                ▼
                ┌──────────────────────────────────┐
                │     Long-polling（空闲态）         │ ← 默认初始态
                │     GET /v1/realtime/poll          │
                │     覆盖：inbox 角标 / 系统通知     │
                │     服务端资源：0（HTTP 无状态）     │
                └───────┬──────────────┬───────────┘
                        │              │
           用户进入聊天页面       10s 内收到 3+ 条消息
           或发送消息            (密集消息触发)
                        │              │
                        ▼              ▼
                ┌──────────────────────────────────┐
                │     WebSocket（活跃态）            │ ← 实时通道
                │     wss://gateway/ws               │
                │     覆盖：消息流 + inbox + 系统通知  │
                │     服务端资源：goroutine + fd       │
                └───────┬──────────────┬───────────┘
                        │              │
           离开聊天页面           60s 无消息收发
           (回到列表/其他页)     (会话沉寂)
                        │              │
                        ▼              ▼
                ┌──────────────────────────────────┐
                │     Long-polling（空闲态）         │ ← 释放 WebSocket
                └───────────────┬──────────────────┘
                                │
                      App 进入后台
                                │
                                ▼
                ┌──────────────────────────────────┐
                │     Disconnected（后台态）         │
                │     仅 APNs/FCM 推送唤醒           │
                │     服务端资源：0                   │
                └───────────────┬──────────────────┘
                                │
                      用户点击通知 / App 回到前台
                                │
                                ▼
                        Long-polling（空闲态）
```

**状态转换触发器**：

| 转换 | 触发条件 | 端侧行为 |
|---|---|---|
| 空闲 → 活跃 | 进入 ChatDetailPage / 发送消息 / 10s 内收到 3+ 条消息 | 建立 WebSocket，停止 long-polling |
| 活跃 → 空闲 | 离开 ChatDetailPage / **`ws_idle_timeout_sec`** 无消息收发（默认 120s） | 关闭 WebSocket，启动 long-polling |
| 任意 → 后台 | App 进入后台（iOS ~3s / Android ~30s） | 关闭所有连接 |
| 后台 → 空闲 | App 回到前台 / 点击 push 通知 | 启动 long-polling + seq gap fill |
| 后台 → 活跃 | 点击消息 push → 直接打开聊天页 | 直接建立 WebSocket + seq gap fill |

**系统级配置参数**（`runtime/config` 统一管理，运维可热更新）：

| 参数 | 默认值 | 说明 |
|---|---|---|
| `realtime.ws_idle_timeout_sec` | **120** | WebSocket 活跃态沉寂阈值：无消息收发超过此秒数 → 关闭 WebSocket 回落空闲态 |
| `realtime.poll_interval_sec` | **60** | Long-polling 空闲态心跳间隔：每次 poll 的 server hold 超时，等效心跳握手 |
| `realtime.ws_heartbeat_sec` | 30 | WebSocket 心跳间隔（活跃态 ping/pong） |
| `realtime.ws_heartbeat_timeout_sec` | 90 | WebSocket 心跳超时（无 pong → 断线） |
| `realtime.ws_max_connections_per_node` | 50000 | 单节点 WebSocket 最大连接数 |
| `realtime.ws_max_connections_per_user` | 5 | 单用户最大 WebSocket 并发连接（多设备） |
| `realtime.ws_write_buffer_warn_bytes` | 65536 | 写缓冲预警阈值（64KB） |
| `realtime.ws_write_buffer_max_bytes` | 262144 | 写缓冲溢出阈值（256KB） |
| `realtime.ws_upgrade_retry_sec` | 60 | WebSocket 被拦截时重试升级间隔 |
| `realtime.active_trigger_msg_count` | 3 | 空闲态收到 N 条消息在 10s 内触发升级活跃态 |
| `realtime.active_trigger_window_sec` | 10 | 密集消息触发窗口 |

端侧通过 App 启动时从 `/v1/config/realtime` 拉取上述参数，运营可在不发版的情况下调整自适应策略。

**WebSocket Upgrade 失败时（代理/防火墙拦截）**：
空闲态和活跃态均使用 long-polling，自动重试 WebSocket Upgrade（60s 间隔），
成功后活跃态升级到 WebSocket，空闲态继续 long-polling。

**资源对比**：

| 状态 | 服务端资源/用户 | 延迟 | 适用 |
|---|---|---|---|
| WebSocket（活跃） | goroutine + fd + ~26KB | < 5ms | 正在聊天的用户（~10-20% 在线） |
| Long-polling（空闲） | **0**（请求结束即释放） | < 30s | 在 App 中但未聊天（~60-70% 在线） |
| Disconnected（后台） | **0** | push 通知 | 后台用户（~20-30%） |

**容量收益**：10 万 DAU、3 万同时在线 → WebSocket 连接仅 ~5K（活跃聊天），
而非 3 万（全部在线），服务端资源降低 **83%**。

**Long-polling 协议**：
- 端点：`GET /v1/realtime/poll?topics=inbox,system&lastSeq={maxInboxSeq}&timeout={poll_interval_sec}`
- 服务端 hold 连接：有新消息 → 立即返回；超时 → 返回 204
- 客户端收到响应后**立即重新发起**下一次 poll
- 空闲态只订阅 `inbox` 和 `system` topic（不订阅具体 conversation）
- 收到 inbox 更新含 conversationId + lastSeq，端侧据此更新角标
- 每次 poll 等效一次心跳握手，服务端据此判定用户仍在 App 中

**HTTP 轮询（SyncMessages API 兜底）**：
当 long-polling 也无法建立时（极端受限网络），客户端退化为定时调用
`POST /v1/chat/conversations/{id}/sync`，间隔 5~30s。

### 4.0.1 SSE 与自适应传输共存说明

| 通道 | 用途 | 生命周期 | 与自适应传输关系 |
|---|---|---|---|
| WebSocket | 聊天消息实时推送 | 活跃态期间 | 自适应传输的活跃通道 |
| Long-polling | inbox 角标/系统通知 | 空闲态期间 | 自适应传输的空闲通道 |
| SSE (runtime/streaming) | AI Assistant 流式 token 输出 | 单次 AI 请求 | **独立共存**，不受自适应传输影响 |

SSE 和自适应传输**完全独立**：SSE 是请求级短命连接（AI 回答完即关闭），
自适应传输是 App 级状态机。两者不冲突，不互斥。
SSE/WebSocket/Long-polling 均由端侧主动发起连接，**不需要端侧暴露公网 IP**。

### 4.0.2 连接资源预算

| 资源 | 单 WebSocket 开销 | 单节点 50K 活跃连接 | 说明 |
|---|---|---|---|
| goroutine | ~8KB（读+写各 1 个） | ~400MB | Go runtime 自动扩栈 |
| file descriptor | 1 fd | 50K fd | 需 `ulimit -n 100000` |
| TCP 缓冲区 | ~16KB（读 8K + 写 8K） | ~800MB | 可调 `net.core.rmem_default` |
| 应用状态 | ~2KB（userId/topics/lastSeq） | ~100MB | 内存 map |
| **合计** | ~26KB | **~1.3GB** | |

Long-polling 请求不占用持久资源（HTTP handler 处理完即释放），因此：
- 50K 活跃 WebSocket + 200K 空闲 long-polling = 仅 ~1.3GB 服务端内存
- 纯 WebSocket 方案同等 250K 用户 = ~6.5GB，差距 **5x**

**per-user 限制**：
- 单用户最多 5 个并发 WebSocket 连接（多设备）
- 超出后踢掉最早的连接（发送 `connection_replaced` 帧）
- Long-polling 无连接数限制（无状态）

**per-node 限制**：
- WebSocket 达 80% 容量（40K）→ 负载均衡器标记 draining
- WebSocket 达 100% → 拒绝新 Upgrade，客户端停留在 long-polling

### 4.0.3 写缓冲区背压处理

当 WebSocket 客户端读取速度跟不上推送速度时（弱网/后台冻结）：

| 阶段 | 条件 | 处理 |
|---|---|---|
| 正常 | 写缓冲 < 64KB | 正常推送 |
| 预警 | 写缓冲 64KB~256KB | 合并同 topic 消息，只推最新 |
| 溢出 | 写缓冲 > 256KB 持续 10s | 断开连接 → 端侧自动回落到 long-polling → 重连后 gap fill |

### 4.1 WebSocket 协议帧格式

```json
{
  "type": "message|subscribe|unsubscribe|heartbeat|ack",
  "topic": "conversation/{id}",
  "payload": { ... },
  "eventId": "optional-for-resume",
  "seq": 12345
}
```

### 4.2 Topic 命名规范

| Topic 模式 | 说明 | 示例 |
|---|---|---|
| `conversation/{conversationId}` | 会话消息 | `conversation/6654a3...` |
| `inbox/{userId}` | 用户会话列表变更 | `inbox/user_001` |
| `system/config` | 运营配置（V2） | `system/config` |
| `channel/{channelId}` | 外部渠道同步 | `channel/feishu_001` |

### 4.3 心跳与断线

- 客户端每 30s 发送 `ping`，服务端回复 `pong`
- 服务端 90s 无心跳 → 标记连接死亡，清除在线状态
- 客户端断线 → 指数退避重连（1s, 2s, 4s, 8s, 16s, max 30s）
- 重连时携带 `lastSeq` 用于 gap fill 判定

### 4.4 鉴权

- WebSocket 建连时通过 URL query param 携带 JWT token
- 服务端验证 token → 提取 userId → 绑定连接
- Token 过期 → 服务端发送 `auth_expired` 帧 → 客户端刷新 token 后重连

### 4.5 跨节点消息路由

```
chat-service → Redis Pub/Sub (channel: rt:conversation:{id})
    → gateway-node-A (用户 X 在此节点) → WebSocket push
    → gateway-node-B (用户 Y 在此节点) → WebSocket push
```

## 5. 性能目标

| 指标 | 目标 | 说明 |
|---|---|---|
| 单节点并发连接 | 100K | 基于 goroutine + epoll |
| 消息 fanout 延迟（节点内） | < 5ms p99 | Redis Pub/Sub → WebSocket write |
| 心跳处理吞吐 | 500K/s per node | 异步批处理 |
| 建连握手耗时 | < 50ms p95 | 含 JWT 验证 |
| 故障切换（节点宕机） | < 30s 客户端重连到新节点 | 指数退避 |

## 6. 约束

- 必须使用 `runtime/config`、`runtime/observability`、`runtime/http`（健康检查端点）
- 禁止在 realtime-gateway 中直接操作 MongoDB（只消费事件，不读写业务数据）
- WebSocket 帧格式必须全局统一（所有 topic 共用）
- 外部渠道 Adapter 必须实现 `ChannelAdapter` SPI interface
- 连接状态必须存储在 Redis（支持多节点查询在线状态）
- realtime-gateway 必须独立部署，禁止与 chat-service 混部

## 7. 验收标准

| 编号 | 条件 | 验证层 |
|---|---|---|
| G-A1 | WebSocket 建连 + 鉴权 + 心跳完整生命周期 | L2 |
| G-A2 | 订阅 conversation topic 后收到该会话新消息推送 | L2 |
| G-A3 | 1000 连接同时订阅同一 topic，消息 fanout < 500ms p99 | L2 基准 |
| G-A4 | 断线后指数退避重连，重连后收到 gap 消息 | L2+L3 |
| G-A5 | 多节点部署，跨节点消息路由正确（Redis Pub/Sub） | L2 |
| G-A6 | 飞书 Webhook 消息经 adapter 路由到端侧 | L2 |
| G-A7 | system/config topic 骨架注册，端侧 handler 可接收空帧 | L3 |
| G-A8 | Prometheus 指标（连接数、消息吞吐、延迟）可采集 | L2 |
| G-A9 | make gate-full 通过（含 realtime-gateway 契约测试） | L1~L2 |
| G-A10 | WebSocket 连接失败时自动降级到 long-polling，消息不丢 | L2+L3 |
| G-A11 | 单用户 > 5 连接时踢掉最早连接，发送 connection_replaced | L2 |
| G-A12 | 节点达 80% 容量时拒绝新连接返回 503 + Retry-After | L2 |
| G-A13 | 写缓冲溢出 > 256KB 持续 10s → 断开连接，客户端重连后 gap fill | L2 |

## 8. 端侧集成

### 8.1 Dart RealtimeConnectionManager

```
lib/cloud/services/realtime/
├── realtime_connection_manager.dart  # WebSocket 生命周期管理
├── realtime_message_handler.dart     # Topic → Handler 路由
└── realtime_config.dart              # 网关地址、心跳间隔等配置
```

职责：
- **自适应传输状态机**：管理 空闲(long-polling) ↔ 活跃(WebSocket) ↔ 后台(disconnected) 转换
- WebSocket 建连 / 心跳 / 重连 / token 刷新（活跃态）
- Long-polling 发起 / 响应处理 / 重连（空闲态）
- Topic 订阅/退订（空闲态仅 inbox+system，活跃态加入 conversation）
- 消息分发到注册的 handler（ChatMessageHandler, InboxHandler, ConfigHandler）
- 状态转换时自动 seq gap fill（确保消息零丢失）
- App lifecycle 感知（前台/后台切换触发状态转换）

### 8.2 Provider 集成

```dart
final realtimeManagerProvider = Provider<RealtimeConnectionManager>((ref) {
  final mode = ref.watch(appDataSourceModeProvider);
  return mode == AppDataSourceMode.remote
      ? RemoteRealtimeConnectionManager(...)
      : MockRealtimeConnectionManager();
});
```

## 9. 跨特性依赖

| 依赖 | 方向 | 说明 |
|---|---|---|
| chat-service | ← | 消费 MessageSent/MemberJoined 等事件 |
| notification-service | → | 离线用户触发 APNs/FCM |
| runtime/config | ← | 读取网关配置 |
| runtime/observability | ← | 指标 + 日志 + tracing |
| unified-entry-security (authn) | ← | JWT 验证复用 |
