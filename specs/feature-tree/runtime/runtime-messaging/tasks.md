# 开发任务：runtime-messaging

**实现状态：COMPLETE** (基础 envelope 和 MQ 中间件完成，53 行代码)

- [x] 实现：MessageEnvelope + MessageMeta — `runtime/messaging/messaging.go`
- [x] 实现：WrapMQConsumer/WrapMQPublisher（delegate to observability）
- [ ] 实现：幂等消费（dedup by messageId）（L4）
- [ ] 实现：重试 + DLQ 策略（L4）
- [ ] 实现：Outbox/Inbox 一致性模式（L5）
- [ ] 测试：envelope 序列化/反序列化单元测试
- [ ] 测试：幂等消费契约测试
- [ ] gate：集成到 make gate
