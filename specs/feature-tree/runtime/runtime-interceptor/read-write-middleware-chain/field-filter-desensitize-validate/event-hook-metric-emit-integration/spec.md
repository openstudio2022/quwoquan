# L5 横切：event-hook-metric-emit-integration

## 功能说明
- **Event Hook**：实体 Save 成功后，根据 events.yaml 自动发布领域事件（如 PostCreated），集成 EventPublisher。
- **Metric Emit**：observe_metric=true 的字段变更自动产生 OTEL metric，供监控和告警使用。
- **Ops Integration**：ops_exposure 控制运营后台字段可见性，与 product-ops 集成。

## 实现要点
- **Event Hook**：写链在 Save 成功后调用 EventPublisher.Publish，payload 不含 SECRET 字段。
- **Metric Emit**：按 observe_metric 配置，字段变更时调用 OTEL Counter/Histogram。
- **Ops**：运营后台查询时应用 ops_exposure 过滤，与读链类似但策略独立。

## 约束
- 事件 payload 不含 SECRET 字段。
- 指标发射不阻塞主流程，可异步。

## 验收标准
- A1：Post Save 触发 PostCreated 事件；observe_metric 字段产生指标。
- A4：OTEL metric 正确产生。
- A5：ops_exposure 控制运营可见性。
- A8：事件/指标单元测试 + 契约测试。
