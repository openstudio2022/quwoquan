# 开发任务：five-core-projectors-implementation

- [ ] 实现：DiscoveryFeedProjector（PostCreated → discovery_feed）
- [ ] 实现：CircleFeedProjector（圈子动态 → circle_feed）
- [ ] 实现：ChatInboxProjector（MessageSent → chat_inbox + 未读计数）
- [ ] 实现：UserProfileViewProjector（用户画像 → user_profile_view）
- [ ] 实现：RecommendFeatureProjector（行为信号 → recommend_feature）
- [ ] 实现：_projections/*.yaml 定义（5 个 ReadModel 结构）
- [ ] 测试：DiscoveryFeedProjector 契约测试
- [ ] 测试：CircleFeedProjector 契约测试
- [ ] 测试：ChatInboxProjector 契约测试
- [ ] 测试：UserProfileViewProjector 契约测试
- [ ] 测试：RecommendFeatureProjector 契约测试
- [ ] gate：集成到 make gate

## Folded legacy node `catchup-idempotency-and-lag-monitoring`

# 开发任务：catchup-idempotency-and-lag-monitoring

- [ ] 实现：offset 持久化（Kafka/Redis 等）
- [ ] 实现：追赶逻辑（批量拉取 + 批量处理）
- [ ] 实现：幂等消费（event_id 或 aggregate_id+version 去重）
- [ ] 实现：消费延迟 metric（OTEL）
- [ ] 实现：消费积压量（lag）metric
- [ ] 集成：runtime-observability 绑定
- [ ] 测试：幂等消费契约测试
- [ ] 测试：追赶能力集成测试
- [ ] gate：集成到 make gate

## 当前交付任务
- [ ] Migrated legacy node: `catchup-idempotency-and-lag-monitoring` (from `runtime/runtime-projector/projector-framework-and-readmodel/five-core-projectors-implementation/catchup-idempotency-and-lag-monitoring`)
