# 开发任务：event-replay-and-schema-evolution

- [ ] 实现：EventStore.Replay(aggregate_id, from_version) 接口
- [ ] 实现：Replay 分页（offset/limit 或 cursor）
- [ ] 实现：events.yaml schema_version 声明
- [ ] 实现：upcaster 逻辑（旧版本 → 新版本）
- [ ] 实现：Projector 重建流程（Replay 全量 → 顺序 Handle）
- [ ] 测试：Replay 契约测试
- [ ] 测试：Schema 版本演进单元测试
- [ ] gate：集成到 make gate
