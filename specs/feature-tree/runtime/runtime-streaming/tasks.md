# 开发任务：runtime-streaming

- [x] 设计：SSEServer 接口（Connect/Send/Broadcast） → `runtime/streaming/sse.go`
- [x] 实现：SSEServer — 连接管理 + userId 路由 + send/broadcast → `runtime/streaming/sse.go`
- [x] 实现：背压机制（慢客户端缓冲区上限 + 超时断开） → `runtime/streaming/sse.go`
- [x] 实现：ChangeStreamWatcher — MongoDB Change Stream 监听 + 事件分发 → `runtime/streaming/changestream.go`
- [x] 集成：SSE 注册到 HTTP 框架 → `runtime/streaming/sse.go`
- [x] 测试：SSE server 集成测试（连接/推送/断开/重连） → `runtime/streaming/sse_test.go`
- [x] 测试：Change Stream watcher 集成测试 → `runtime/streaming/sse_test.go`
- [x] gate：集成到 make gate
