# L4 对象任务：five-core-projectors-implementation

## 功能说明
- **DiscoveryFeedProjector**：消费 PostCreated 等事件，更新 discovery_feed ReadModel（内容发现信息流）。
- **CircleFeedProjector**：消费圈子内 PostCreated，更新 circle_feed ReadModel（圈子动态流）。
- **ChatInboxProjector**：消费 MessageSent、ConversationCreated 等，更新 chat_inbox ReadModel（收件箱 + 未读计数）。
- **UserProfileViewProjector**：消费 UserProfileUpdated、FollowCreated 等，更新 user_profile_view ReadModel（用户画像聚合视图）。
- **RecommendFeatureProjector**：消费 view/like/dislike 等行为信号，更新 recommend_feature ReadModel（推荐特征聚合）。

## 实现要点
- **每个 Projector**：实现 Handle(ctx, event)；按 event 类型更新对应 ReadModel 集合。
- **幂等**：通过 event_id 或 (aggregate_id, version) 去重。
- **ReadModel 存储**：MongoDB 集合，结构与 _projections/*.yaml 一致。

## 约束
- ReadModel 结构必须与 _projections/*.yaml 一致。
- 每个 Projector 必须幂等。

## 验收标准
- A1：5 个 Projector 事件消费 → ReadModel 验证正确。
- A8：每个 Projector 有契约测试。

## Folded legacy node `catchup-idempotency-and-lag-monitoring`

# L5 横切：catchup-idempotency-and-lag-monitoring

## 功能说明
- **追赶能力**：Projector 重启或长时间停机后，能从 offset 恢复消费，不遗漏事件；支持批量消费加速追赶。
- **幂等保证**：通过 event_id 或 (aggregate_id, version) 去重；重复消费同一事件不产生副作用。
- **延迟与积压监控**：消费延迟（event 产生到消费完成）、消费积压量（lag）可监控；接入 runtime-observability。

## 实现要点
- **追赶**：offset 持久化；恢复时从 offset 继续；批量拉取（batch_size）加速追赶。
- **幂等**：消费前检查 event_id 是否已处理；已处理则跳过；更新 ReadModel 时使用 upsert 或条件更新。
- **监控**：消费延迟 metric、lag metric；接入 OTEL。

## 约束
- 幂等逻辑必须覆盖所有 Projector。
- 监控不暴露 PII。

## 验收标准
- A3：at-least-once + 幂等 + 追赶能力。
- A4：消费延迟和积压量可监控。
- A8：幂等和追赶均有测试。
