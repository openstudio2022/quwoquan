# 开发任务：mongo-event-collection-and-mq-integration

- [ ] 实现：MongoDB events 集合存储（Persist + QueryByAggregateID）
- [ ] 实现：events 集合索引（aggregate_id, timestamp）
- [ ] 实现：RocketMQ 生产者集成（events topic）
- [ ] 实现：Outbox 表（outbox 集合/表）
- [ ] 实现：Outbox 定时投递任务（扫描 + 投递 + 删除）
- [ ] 测试：MongoDB 持久化契约测试（testcontainers）
- [ ] 测试：RocketMQ 发布契约测试（EventSpy）
- [ ] gate：集成到 make gate
