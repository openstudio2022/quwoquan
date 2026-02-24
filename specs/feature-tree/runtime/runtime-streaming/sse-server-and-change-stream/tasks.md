# 开发任务：sse-server-and-change-stream

- [ ] 设计：SSEServer 接口（Connect/Push/Disconnect/Broadcast）
- [ ] 实现：SSEServer — 连接管理 + userId 路由 + Last-Event-ID 续传
- [ ] 实现：ChangeStreamWatcher — MongoDB Change Stream 监听 + 事件分发
- [ ] 实现：Change Stream → SSE 事件映射（events.yaml 类型）
- [ ] 集成：SSE 注册到 HTTP 框架（GET /v1/stream/events）
- [ ] 测试：SSE server 集成测试（连接/推送/断开）
- [ ] 测试：Change Stream watcher 集成测试（testcontainers mongo）
- [ ] gate：集成到 make gate
