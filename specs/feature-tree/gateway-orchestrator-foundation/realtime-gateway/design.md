# realtime-gateway 设计方案

## 设计动因

当前实时推送完全依赖 SSE（runtime/streaming），仅支持 AI Assistant 单向流式输出，无法满足聊天双向实时、在线感知、大群 fanout 和外部渠道接入需求。飞书/Discord/Slack 均采用独立 WebSocket 网关与业务服务解耦的架构。

## 上游输入评审

- spec.md：清晰完整，V1 功能 G1~G12 已明确，自适应传输状态机、系统配置参数、连接资源预算均已基线化
- acceptance.yaml：G-A1~G-A13 + G-A10b 覆盖全链路，可测量
- 依赖项：runtime-redis（realtime scene 提供 Pub/Sub + 在线状态） — 已 design 基线
- 无阻断项

## 对标输入分析

| 对标 | 借鉴 | 不借鉴 | 适用边界 |
|---|---|---|---|
| Discord Gateway | goroutine-per-conn + epoll + topic 扇出 | 私有压缩协议（我们用 JSON 帧） | 10K~100K 连接/节点 |
| 飞书长连接网关 | JWT 鉴权 + 心跳超时 + 多节点 Redis Pub/Sub | 私有 protobuf 帧（V1 先用 JSON，V2 可选 msgpack） | 企业级可靠性 |
| Socket.io | Namespace/Room 概念 → Topic 路由 | 自动降级到 polling 的粗粒度策略 | 我们用**活跃度自适应**替代粗粒度降级 |
| Slack RTM | 统一帧格式 + 事件类型枚举 | 单 WebSocket 无 topic 过滤 | 我们按 topic 精准订阅 |

## 方案对比

### 方案 A：独立 Go 服务 + goroutine-per-conn + Redis Pub/Sub 跨节点（选定）

realtime-gateway 作为独立 Go 服务，使用 gorilla/websocket + goroutine-per-conn，
跨节点消息通过 Redis Pub/Sub 广播，在线状态存 Redis。

**优点**：
- Go 天然适合高并发长连接（goroutine 轻量）
- 与 chat-service 完全解耦，独立扩缩
- Redis Pub/Sub 跨节点路由成熟可靠
- 自适应传输状态机在 gateway 层统一管理，业务服务无感知

**缺点**：
- 新增独立服务，运维复杂度 +1
- 跨节点 fanout 有 Redis 中转延迟（< 1ms 可接受）
- 需要处理 WebSocket 连接状态一致性

**适用条件**：需要 > 10K 并发连接、多服务共用实时通道

### 方案 B：chat-service 内嵌 WebSocket（不选）

在 chat-service 中直接处理 WebSocket。

**优点**：无需新服务，少一跳
**缺点**：
- chat-service 既做消息持久化又做连接管理，职责混乱
- 无法为其他服务（外部渠道、运营配置）提供实时通道
- 连接与业务耦合，无法独立扩缩
- 违背 spec 约束"realtime-gateway 必须独立部署"

## 选型决策

**选定方案 A**：独立 Go 服务 + Redis Pub/Sub。

理由：realtime-gateway 定位为平台级基础设施，不仅服务聊天，还承载外部渠道和运营配置。
独立服务允许连接层和业务层独立扩缩，符合 spec 中"平台级"和"独立部署"约束。

## 关键设计决策

### KD-1：服务结构

```
services/realtime-gateway/
├── cmd/api/main.go
├── internal/
│   ├── domain/
│   │   ├── connection.go         # Connection 实体（connId, userId, topics, transport, writeBuffer）
│   │   ├── connection_events.go  # 连接事件（Connected, Disconnected, TopicSubscribed）
│   │   └── topic.go              # Topic 实体（pattern, subscribers）
│   ├── application/
│   │   ├── hub_service.go        # Hub：连接注册/注销 + topic 路由 + fanout
│   │   └── transport_service.go  # 自适应传输状态管理
│   ├── adapters/
│   │   ├── http/
│   │   │   ├── ws_handler.go     # WebSocket Upgrade + 帧读写
│   │   │   ├── poll_handler.go   # Long-polling 端点 GET /v1/realtime/poll
│   │   │   └── channel_webhook_handler.go  # 外部渠道 Webhook 入口
│   │   └── mq/
│   │       └── redis_subscriber.go  # Redis Pub/Sub 消费 → Hub.Broadcast
│   └── infrastructure/
│       ├── persistence/
│       │   └── redis_presence.go  # 在线状态存储（presence:user:{uid}）
│       └── cache/
│           └── transport_state_cache.go  # 用户传输状态缓存
├── configs/config.yaml
├── go.mod
└── Makefile
```

### KD-2：Hub 核心数据结构

```go
type Hub struct {
    mu          sync.RWMutex
    connections map[string]*Connection          // connId → Connection
    userConns   map[string]map[string]struct{}   // userId → {connId set}
    topicSubs   map[string]map[string]struct{}   // topic → {connId set}
    
    config      *RealtimeConfig
    presence    PresenceStore
    metrics     *Metrics
}
```

- `Register(conn)` → 检查 per-user 限制 → 踢最早连接 → 注册
- `Unregister(connId)` → 清理 topic 订阅 → 更新 presence
- `Subscribe(connId, topic)` → 加入 topicSubs
- `Broadcast(topic, payload)` → 遍历 topicSubs[topic] → 逐连接 write

### KD-3：自适应传输实现

```
Transport State Machine (per-user, per-device)
┌─────────────────────────────────────────────────┐
│  TransportState: IDLE | ACTIVE | BACKGROUND      │
│  CurrentTransport: WEBSOCKET | LONG_POLL | NONE  │
└─────────────────────────────────────────────────┘
```

**服务端职责**：
- 维护 presence（在线/离线/transport 类型）
- Long-polling 端点：hold 连接 ≤ poll_interval_sec，有消息立即返回，超时 204
- WebSocket 端点：正常帧读写 + 心跳
- 用户的 topic 订阅在 transport 切换时迁移（WebSocket → poll 时 topic 收窄为 inbox+system）

**端侧职责**：
- 状态机驱动 transport 切换（进入聊天页/离开/后台等触发）
- WebSocket idle 计时器（ws_idle_timeout_sec）
- Long-polling 自动重连循环

### KD-4：Long-polling 实现

```go
func (h *PollHandler) HandlePoll(w http.ResponseWriter, r *http.Request) {
    userId := auth.UserIdFromContext(r.Context())
    topics := r.URL.Query()["topics"]  // inbox,system
    lastSeq := r.URL.Query().Get("lastSeq")
    timeout := parseTimeout(r.URL.Query().Get("timeout"), h.config.PollIntervalSec)
    
    // 创建临时通道
    ch := h.hub.CreatePollChannel(userId, topics)
    defer h.hub.RemovePollChannel(userId, ch)
    
    select {
    case msgs := <-ch:
        json.NewEncoder(w).Encode(PollResponse{Messages: msgs})
    case <-time.After(timeout):
        w.WriteHeader(http.StatusNoContent) // 204 = 无新消息 = 心跳
    case <-r.Context().Done():
        return
    }
}
```

### KD-5：写缓冲背压

每个 Connection 维护 `writeBuffer chan []byte`（带缓冲），
write goroutine 消费 → WebSocket write：

| 阶段 | 条件 | 处理 |
|---|---|---|
| 正常 | buffer len < warn | 直接 write |
| 预警 | warn ≤ buffer len < max | 合并同 topic 消息，只推最新 seq |
| 溢出 | buffer len ≥ max 且持续 10s | 关闭连接，端侧回落 long-polling |

### KD-6：外部渠道 Adapter SPI

```go
type ChannelAdapter interface {
    Name() string                              // "feishu", "dingtalk", ...
    ValidateWebhook(r *http.Request) error     // 签名/Token 验证
    ParsePayload(body []byte) (*UnifiedFrame, error) // 转换为统一帧
    TargetTopic(frame *UnifiedFrame) string    // 路由到哪个 topic
}
```

V1 实现 `FeishuAdapter`，其余 adapter 按需注册。

### KD-7：可观测指标

| 指标 | 类型 | 标签 |
|---|---|---|
| `realtime_connections_active` | gauge | transport={ws,poll}, node |
| `realtime_messages_sent_total` | counter | topic_type, transport |
| `realtime_message_fanout_duration_seconds` | histogram | topic_type |
| `realtime_heartbeat_timeouts_total` | counter | — |
| `realtime_write_buffer_overflows_total` | counter | — |
| `realtime_poll_requests_total` | counter | status={200,204} |
| `realtime_transport_transitions_total` | counter | from, to |

## Story 与测试层映射

| Story | 内容 | 测试层 |
|---|---|---|
| S1 | WebSocket 生命周期（建连/鉴权/心跳/断线） | L2：Go test ws.Dial + auth + heartbeat |
| S2 | Topic 订阅 + 消息 fanout | L2：订阅 → publish → assert receive |
| S3 | 跨节点 Redis Pub/Sub 路由 | L2：2 实例 + miniredis |
| S4 | Long-polling 端点 | L2：poll + timeout + 消息即时返回 |
| S5 | 自适应传输状态机 | L2+L3：状态转换序列测试 |
| S6 | per-user / per-node 资源限制 | L2：超限踢连接 + 503 |
| S7 | 写缓冲背压 | L2：慢客户端 → 合并 → 断连 |
| S8 | 飞书 Webhook Adapter | L2：POST webhook → ws receive |
| S9 | 端侧 RealtimeConnectionManager | L3：Dart unit test 状态机 |
| S10 | 可观测指标 | L2：/metrics 端点验证 |

## 未来演进

- **protobuf/msgpack 压缩帧**：触发 JSON 帧占带宽 > 30% 时
- **连接迁移（无损漂移）**：触发需节点滚动更新频率 > 1 次/天
- **多区域就近接入**：触发海外用户 > 10% DAU
- **config-push V2**：运营配置推送完整实现（feature flag / UI 配置 / 策略热更新）

## 遗留带规划任务

- config-push V2 实现（与 tasks.md 搁置任务对应）
- 消息压缩从 JSON 升级到 protobuf（与性能优化迭代对应）
