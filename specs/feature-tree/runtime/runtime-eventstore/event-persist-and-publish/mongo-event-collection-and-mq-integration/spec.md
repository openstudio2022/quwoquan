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
