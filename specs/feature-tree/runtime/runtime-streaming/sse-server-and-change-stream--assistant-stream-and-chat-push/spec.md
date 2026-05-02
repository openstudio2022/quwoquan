# L4 对象任务：assistant-stream-and-chat-push

## 功能说明
- **助手流式输出**：QA Runner 生成回复时，通过 SSEServer 逐 chunk 推送给对应用户；事件类型 assistant.chunk。
- **聊天消息推送**：message.sent 事件产生后，ChangeStreamWatcher 监听 messages 集合变更，触发 SSEServer.Push 给接收方用户。
- **动态更新推送**：Post 发布后，订阅用户的 SSE 连接收到 feed.updated 推送。

## 实现要点
- **助手流式**：QA Runner 回调 SSEServer.Push(userId, chunk)；chunk 格式与 events.yaml 一致。
- **聊天推送**：Change Stream 监听 messages 集合；insert 事件 → 解析 recipient_id → Push。
- **动态推送**：Change Stream 监听 posts 或 feed 相关集合；按订阅关系路由。

## 约束
- 推送事件类型与 events.yaml 定义一致。
- 按 userId 隔离，不跨用户泄露。

## 验收标准
- A1：助手流式输出 + 聊天消息推送端到端可用。
- A2：推送延迟 < 100ms（本地环境）。
- A8：助手流式 + 聊天推送端到端测试。

## Folded current node `backpressure-and-reconnection`

# L5 横切：backpressure-and-reconnection

## 功能说明
- **背压机制**：慢客户端缓冲区达到上限时，暂停推送或断开连接；防止慢客户端阻塞服务端和其他用户。
- **断线重连**：客户端携带 Last-Event-ID 重连时，服务端从该事件 ID 续传，不丢失消息。
- **超时断开**：慢客户端超时未消费时自动断开，释放资源。

## 实现要点
- **背压**：每个 SSE 连接维护发送缓冲区；缓冲区满时阻塞或断开；可配置 buffer_size、timeout。
- **Last-Event-ID**：SSE 标准头；服务端记录每个事件的 ID；重连时根据 ID 查询续传事件。
- **Change Stream resume**：Change Stream 的 resume token 持久化，服务重启后可续传。

## 约束
- 背压参数可配置（buffer_size、timeout）。
- Last-Event-ID 与事件 ID 一致（events.yaml 或内部 ID）。

## 验收标准
- A3：连接数上限 + 背压 + 超时断开。
- A2：断线重连不丢失消息。
- A8：背压 + 重连集成测试。
