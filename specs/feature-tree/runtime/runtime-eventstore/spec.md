# L2 特性：runtime-eventstore

## 功能说明
- MongoDB events 集合持久化领域事件（aggregate_id, event_type, payload, timestamp, trace_id）。
- 集成 RocketMQ 发布事件到消息队列。
- 写路径集成：Repository.Save() 后自动 persist event + publish MQ。
- Outbox 模式保证事件发布的最终一致性。

## 约束
- 事件 schema 必须与 events.yaml 定义一致。
- 事件 payload 必须遵循 fields.yaml 的 classification 策略。
- 事件必须包含 OTEL traceID。

## 验收标准
- A1：Post.Save() → event 写入 MongoDB + 发布到 MQ。
- A3：Outbox 模式保证最终一致性。
- A7：事件 schema 与 events.yaml 一致。
- A8：持久化 + 发布均有契约测试。
