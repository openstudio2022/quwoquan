# 开发任务：mongo-event-collection-and-mq-integration

- [ ] 实现：MongoDB events 集合存储（Persist + QueryByAggregateID）
- [ ] 实现：events 集合索引（aggregate_id, timestamp）
- [ ] 实现：RocketMQ 生产者集成（events topic）
- [ ] 实现：Outbox 表（outbox 集合/表）
- [ ] 实现：Outbox 定时投递任务（扫描 + 投递 + 删除）
- [ ] 测试：MongoDB 持久化契约测试（testcontainers）
- [ ] 测试：RocketMQ 发布契约测试（EventSpy）
- [ ] gate：集成到 make gate

## Folded legacy node `event-replay-and-schema-evolution`

# 开发任务：event-replay-and-schema-evolution

- [ ] 实现：EventStore.Replay(aggregate_id, from_version) 接口
- [ ] 实现：Replay 分页（offset/limit 或 cursor）
- [ ] 实现：events.yaml schema_version 声明
- [ ] 实现：upcaster 逻辑（旧版本 → 新版本）
- [ ] 实现：Projector 重建流程（Replay 全量 → 顺序 Handle）
- [ ] 测试：Replay 契约测试
- [ ] 测试：Schema 版本演进单元测试
- [ ] gate：集成到 make gate

## 当前交付任务
- [ ] Migrated legacy node: `event-replay-and-schema-evolution` (from `runtime/runtime-eventstore/event-persist-and-publish/mongo-event-collection-and-mq-integration/event-replay-and-schema-evolution`)
