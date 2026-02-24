# 开发任务：catchup-idempotency-and-lag-monitoring

- [ ] 实现：offset 持久化（Kafka/Redis 等）
- [ ] 实现：追赶逻辑（批量拉取 + 批量处理）
- [ ] 实现：幂等消费（event_id 或 aggregate_id+version 去重）
- [ ] 实现：消费延迟 metric（OTEL）
- [ ] 实现：消费积压量（lag）metric
- [ ] 集成：runtime-observability 绑定
- [ ] 测试：幂等消费契约测试
- [ ] 测试：追赶能力集成测试
- [ ] gate：集成到 make gate
