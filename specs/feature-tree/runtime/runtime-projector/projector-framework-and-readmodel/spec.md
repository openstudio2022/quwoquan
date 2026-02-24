# L3 子特性：projector-framework-and-readmodel

## 功能说明
- **Projector 接口**：Handle(ctx, event) error；接收事件，更新 ReadModel。
- **事件消费框架**：MQ consumer 订阅 events topic；按 event_type 路由到对应 Projector；offset 管理。
- **ReadModel 设计**：_projections/*.yaml 定义 ReadModel 集合（discovery_feed、circle_feed、chat_inbox、user_profile_view、recommend_feature）。

## 实现要点
- **接口**：Projector 接口 + 注册表（event_type → Projector）。
- **消费框架**：Consumer 拉取消息 → 反序列化 → 路由 → 调用 Projector.Handle → 提交 offset。
- **幂等**：通过 event_id 或 (aggregate_id, version) 去重，重复消费同一事件不更新。

## 约束
- ReadModel 结构必须与 _projections/*.yaml 一致。
- Projector 必须幂等。

## 验收标准
- A1：消费框架可调用任意 Projector；ReadModel 结构正确。
- A7：ReadModel 与 _projections/*.yaml 一致。
- A8：框架有单元测试。
