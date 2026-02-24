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
