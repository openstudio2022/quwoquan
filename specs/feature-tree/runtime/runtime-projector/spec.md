# L2 特性：runtime-projector

## 功能说明
- Projector 接口 + 事件消费框架（MQ consumer）。
- 5 个核心 Projector：DiscoveryFeedProjector, CircleFeedProjector, ChatInboxProjector, UserProfileViewProjector, RecommendFeatureProjector。
- 对应 ReadModel 集合（定义在 _projections/*.yaml）。

## 约束
- Projector 必须幂等（重复消费同一事件不产生副作用）。
- ReadModel 结构必须与 _projections/*.yaml 一致。

## 验收标准
- A1：事件消费 → ReadModel 正确更新。
- A3：at-least-once + 幂等 + 追赶能力。
- A7：ReadModel 与 _projections/*.yaml 一致。
- A8：每个 Projector 有契约测试。
