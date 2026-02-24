# L2 特性：runtime-streaming

## 功能说明
- **SSEServer**：管理 SSE 连接（Connect/Push/Disconnect/Broadcast），按 userId 路由推送；支持 Last-Event-ID 续传。
- **ChangeStreamWatcher**：监听 MongoDB 集合变更（Change Stream），将变更事件转换为 SSE 推送或内部事件。
- **背压机制**：慢客户端缓冲区上限 + 超时断开，防止阻塞服务端。
- **重连机制**：基于 Last-Event-ID 的断线续传，不丢失消息。
- **HTTP 集成**：GET /v1/stream/events 注册 SSE 连接，需认证。

## 实现要点
- **SSEServer**：连接池按 userId 索引；Push 时广播给该用户所有连接；支持 Last-Event-ID 续传。
- **Change Stream**：监听目标集合（如 messages、assistant_events）；resume token 持久化支持断点续传。
- **事件映射**：Change Stream 文档 → events.yaml 定义的事件类型 → SSE 推送。
- **背压**：每个连接维护缓冲区，达到上限时暂停推送或断开连接。
- **重连**：客户端携带 Last-Event-ID 重连时，服务端从该 ID 续传。

## 约束
- SSE 连接需认证，推送内容按 userId 隔离。
- 背压机制：慢客户端不阻塞服务端。
- 断线自动重连，基于 Last-Event-ID 续传。
- Change Stream 监听集合需在 event_catalog 登记。

## 验收标准
- A1：助手流式输出（SSE逐chunk推送）+ 聊天消息推送（message.sent→SSE push）端到端可用。
- A3：连接数上限 + 背压 + 重连。
- A8：SSE server + Change Stream watcher 集成测试。
