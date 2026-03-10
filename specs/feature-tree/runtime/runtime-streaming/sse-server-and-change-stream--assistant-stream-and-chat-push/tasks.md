# 开发任务：assistant-stream-and-chat-push

- [ ] 实现：助手流式输出 — QA Runner 回调 SSEServer.Push(userId, chunk)
- [ ] 实现：assistant.chunk 事件类型（events.yaml 登记）
- [ ] 实现：聊天消息推送 — Change Stream 监听 messages → Push 给 recipient
- [ ] 实现：message.sent 事件映射与路由
- [ ] 实现：动态更新推送 — Change Stream 监听 posts/feed → 按订阅路由
- [ ] 测试：助手流式输出端到端测试
- [ ] 测试：聊天消息推送端到端测试
- [ ] gate：集成到 make gate

## Folded legacy node `backpressure-and-reconnection`

# 开发任务：backpressure-and-reconnection

- [ ] 实现：背压机制 — 慢客户端缓冲区上限 + 超时断开
- [ ] 实现：SSE 连接发送缓冲区（可配置 buffer_size）
- [ ] 实现：Last-Event-ID 续传 — 记录事件 ID，重连时续传
- [ ] 实现：Change Stream resume token 持久化
- [ ] 实现：连接数上限配置与拒绝策略
- [ ] 测试：背压机制单元测试（缓冲区满、超时断开）
- [ ] 测试：重连续传集成测试（Last-Event-ID）
- [ ] gate：集成到 make gate

## 当前交付任务
- [ ] Migrated legacy node: `backpressure-and-reconnection` (from `runtime/runtime-streaming/sse-server-and-change-stream/assistant-stream-and-chat-push/backpressure-and-reconnection`)
