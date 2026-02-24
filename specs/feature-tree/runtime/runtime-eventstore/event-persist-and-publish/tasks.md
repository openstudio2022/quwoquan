# 开发任务：event-persist-and-publish

- [ ] 设计：Event Store 接口（Persist/Query/Publish）
- [ ] 实现：Persist 持久化到 MongoDB events 集合
- [ ] 实现：Publish 发布到 RocketMQ topic
- [ ] 实现：QueryByAggregateID 按 aggregate_id 查询事件流
- [ ] 集成：Repository 写路径拦截链 → EventStore
- [ ] 测试：事件持久化契约测试（testcontainers mongo）
- [ ] 测试：事件发布契约测试（EventSpy）
- [ ] gate：集成到 make gate
