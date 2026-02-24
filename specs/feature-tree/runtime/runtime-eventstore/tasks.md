# 开发任务：runtime-eventstore

- [x] 设计：Event Store 接口（Append/AppendBatch/LoadEvents/LoadEventsByType/LatestVersion） → `runtime/eventstore/store.go`
- [x] 实现：MongoDB events 集合存储（持久化 + 按 aggregate_id 查询） → `runtime/eventstore/store.go`
- [x] 实现：AppendBatch 批量追加 → `runtime/eventstore/store.go`
- [x] 实现：LoadEventsByType 按事件类型查询 → `runtime/eventstore/store.go`
- [x] 实现：LatestVersion 版本查询 → `runtime/eventstore/store.go`
- [x] 实现：unique indexes 索引创建 → `runtime/eventstore/store.go`
- [x] 集成：Repository 写路径 → 拦截链 → Event Store
- [x] 测试：事件持久化契约测试（testcontainers mongo） → `runtime/eventstore/store_test.go`
- [x] 测试：事件发布契约测试（EventSpy） → `runtime/eventstore/store_test.go`
- [x] gate：集成到 make gate
