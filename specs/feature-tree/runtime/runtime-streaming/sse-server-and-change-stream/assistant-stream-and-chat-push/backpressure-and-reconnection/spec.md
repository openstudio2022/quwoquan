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
