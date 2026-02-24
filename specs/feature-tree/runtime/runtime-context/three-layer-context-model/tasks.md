# 开发任务：three-layer-context-model

- [ ] 设计：三层上下文模型接口（PageContext/SessionContext/LongTermProfile）
- [ ] 设计：ContextAssembler 接口（Assemble(userId) → AssembledContext）
- [ ] 实现：PageContext 结构（8 种场景类型、PostSnapshot、userActions）
- [ ] 实现：SessionContext 结构（实时兴趣信号）
- [ ] 实现：LongTermProfile 结构（五维画像）
- [ ] 实现：ContextAssembler 组装逻辑（三层聚合）
- [ ] 测试：三层模型接口单元测试
- [ ] gate：集成到 make gate
