# L3 子特性：sse-server-and-change-stream

## 功能说明
- **SSEServer**：管理 SSE 连接（Connect/Push/Disconnect/Broadcast），按 userId 路由推送；支持 Last-Event-ID 续传。
- **ChangeStreamWatcher**：监听 MongoDB 集合变更（Change Stream），将变更事件转换为 SSE 推送或内部事件。
- **HTTP 集成**：GET /v1/stream/events 注册 SSE 连接，需认证。

## 实现要点
- **SSEServer**：连接池按 userId 索引；Push 时广播给该用户所有连接。
- **Change Stream**：监听目标集合（如 messages、assistant_events）；resume token 持久化支持断点续传。
- **事件映射**：Change Stream 文档 → events.yaml 定义的事件类型 → SSE 推送。

## 约束
- SSE 连接需认证，推送内容按 userId 隔离。
- Change Stream 监听集合需在 event_catalog 登记。

## 验收标准
- A1：SSE 连接建立 + 推送 + Change Stream 触发端到端正确。
- A3：连接数上限可配置。
- A8：SSE server + Change Stream watcher 集成测试。
