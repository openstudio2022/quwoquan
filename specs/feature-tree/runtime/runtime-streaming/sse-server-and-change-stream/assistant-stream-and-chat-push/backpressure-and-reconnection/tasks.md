# 开发任务：backpressure-and-reconnection

- [ ] 实现：背压机制 — 慢客户端缓冲区上限 + 超时断开
- [ ] 实现：SSE 连接发送缓冲区（可配置 buffer_size）
- [ ] 实现：Last-Event-ID 续传 — 记录事件 ID，重连时续传
- [ ] 实现：Change Stream resume token 持久化
- [ ] 实现：连接数上限配置与拒绝策略
- [ ] 测试：背压机制单元测试（缓冲区满、超时断开）
- [ ] 测试：重连续传集成测试（Last-Event-ID）
- [ ] gate：集成到 make gate
