# 开发任务：test-engine-and-fixture-framework

- [ ] 设计：TestEngine 接口（Start/Stop/Conn/Migrate/Cleanup）
- [ ] 设计：TestSuite 基类（组合多引擎）
- [ ] 设计：Fixture Builder 接口（WithXxx/Build）
- [ ] 设计：EventPublisher Spy 接口（Capture/AssertPublished）
- [ ] 实现：Fixture 从 EntityRegistry 读取 fields 约束
- [ ] 实现：Fixture 默认值生成逻辑
- [ ] 测试：TestSuite 自测
- [ ] 测试：Fixture 自测（生成数据符合约束）
- [ ] gate：集成到 make gate
