# L3 子特性：event-persist-and-publish

## 功能说明
- **Event Store 核心能力**：Persist（持久化到 MongoDB）和 Publish（发布到 RocketMQ）。
- **接口定义**：Persist(event)、Publish(event)、QueryByAggregateID(aggregate_id)。
- **写路径集成**：Repository.Save() 后经过拦截链，自动触发 EventStore.Persist + Publish。

## 实现要点
- **Persist**：写入 MongoDB events 集合，字段 aggregate_id、event_type、payload、timestamp、trace_id。
- **Publish**：序列化事件后发送到 RocketMQ 的 events topic。
- **拦截链**：Repository 写路径拦截器在 Save 成功后调用 EventStore。

## 约束
- 事件 schema 必须与 events.yaml 定义一致。
- 事件必须包含 OTEL traceID。

## 验收标准
- A1：Persist 和 Publish 端到端正确。
- A7：事件 schema 与 events.yaml 一致。
- A8：持久化 + 发布均有契约测试。
