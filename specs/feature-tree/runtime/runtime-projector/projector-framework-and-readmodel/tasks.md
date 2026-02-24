# 开发任务：projector-framework-and-readmodel

- [ ] 设计：Projector 接口（Handle event → update ReadModel）
- [ ] 设计：ReadModel 结构（_projections/*.yaml）
- [ ] 实现：事件消费框架（MQ consumer + offset 管理）
- [ ] 实现：event_type → Projector 路由
- [ ] 实现：幂等消费（event_id 或 aggregate_id+version 去重）
- [ ] 测试：Projector 接口 mock 与框架单元测试
- [ ] gate：集成到 make gate
