# 开发任务：event-hook-metric-emit-integration

- [ ] 实现：写链领域事件发布 hook（按 events.yaml）
- [ ] 实现：EventPublisher 集成（支持 spy 用于测试）
- [ ] 实现：observe_metric 字段变更 OTEL metric 发射
- [ ] 实现：ops_exposure 运营后台字段可见性控制
- [ ] 测试：事件 hook 单元测试（发布/不发布/payload 不含 SECRET）
- [ ] 测试：指标发射单元测试
- [ ] 测试：端到端契约测试（Post 事件 + UserProfile 指标）
- [ ] gate：集成到 make gate
