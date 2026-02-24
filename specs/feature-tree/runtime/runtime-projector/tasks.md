# 开发任务：runtime-projector

- [x] 设计：Projector 接口定义（Handle event → update ReadModel） → `runtime/projector/projector.go`
- [x] 实现：Dispatcher 事件分发框架 → `runtime/projector/projector.go`
- [x] 实现：DiscoveryFeedProjector（内容发现信息流） → `runtime/projector/readmodels.go`
- [x] 实现：ChatInboxProjector（聊天收件箱 + 未读计数） → `runtime/projector/readmodels.go`
- [x] 实现：UserProfileViewProjector（用户画像聚合视图） → `runtime/projector/readmodels.go`
- [x] 实现：RecommendFeatureProjector（推荐特征聚合） → `runtime/projector/readmodels.go`
- [x] 测试：每个 Projector 契约测试（event → ReadModel 验证） → `runtime/projector/projector_test.go`
- [x] gate：集成到 make gate
