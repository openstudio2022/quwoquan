# L4 对象任务：mongo-event-collection-and-mq-integration

## 功能说明
- **MongoDB events 集合**：存储领域事件，字段 aggregate_id、event_type、payload、timestamp、trace_id；索引按 aggregate_id + timestamp。
- **RocketMQ 集成**：生产者发送事件到 events topic；序列化格式与 events.yaml 一致。
- **Outbox 模式**：事件表 + 定时投递任务；发布失败时写入 outbox，重试投递保证最终一致性。

## 实现要点
- **MongoDB**：使用官方 driver，集合名 events，索引 { aggregate_id: 1, timestamp: 1 }。
- **RocketMQ**：使用官方 producer，topic 从 runtime-config 读取。
- **Outbox**：outbox 表存储待发布事件；定时任务扫描 outbox 投递到 MQ，成功后删除。

## 约束
- 事件 schema 必须与 events.yaml 定义一致。
- 契约测试使用 testcontainers（MongoDB）和 EventSpy（MQ）。

## 验收标准
- A1：MongoDB 持久化 + RocketMQ 发布 + Outbox 重试端到端正确。
- A8：持久化 + 发布均有契约测试。

## Folded legacy node `event-replay-and-schema-evolution`

# L5 横切：event-replay-and-schema-evolution

## 功能说明
- **事件重放**：Replay(aggregate_id, from_version) 返回该聚合自 from_version 起的事件流，用于 Projector 重建 ReadModel。
- **Schema 版本演进**：事件 payload 支持 version 字段；旧版本事件通过 upcaster 或默认值兼容解析。
- **分页**：Replay 支持 offset/limit 分页，避免大结果集 OOM。

## 实现要点
- **Replay**：按 aggregate_id + timestamp 查询；支持 from_version 过滤；可配置 batch_size。
- **Schema 演进**：events.yaml 声明 schema_version；upcaster 映射旧版本 → 新版本。
- **Projector 重建**：全量 Replay 后顺序调用 Projector.Handle，重建 ReadModel。

## 约束
- 事件 schema 版本与 events.yaml 定义一致。
- Replay 不修改原始事件，仅读取。

## 验收标准
- A1：Replay 返回正确事件流；支持 schema 版本兼容。
- A7：事件 schema 版本与 events.yaml 一致。
- A8：Replay 和 schema 演进均有测试。
