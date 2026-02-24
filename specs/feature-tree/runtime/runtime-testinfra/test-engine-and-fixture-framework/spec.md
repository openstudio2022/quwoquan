# L3 子特性：test-engine-and-fixture-framework

## 功能说明
- **TestSuite 基类**：抽象测试引擎生命周期（Start/Stop），提供 DB 连接、迁移执行、清理接口。支持 PG/Mongo/Redis 三种引擎的抽象。
- **Fixture 框架**：Builder 模式，从 fields.yaml 约束生成合规测试数据。支持 WithXxx 链式调用，Build() 输出实体。
- **EventPublisher Spy**：捕获发布的领域事件，支持 AssertPublished(eventType, matcher) 断言。

## 实现要点
- **Engine 抽象**：定义 TestEngine 接口（Start/Stop/Conn/Migrate/Cleanup），各引擎实现此接口。
- **Fixture 设计**：按 entity 从 EntityRegistry 获取 fields，生成默认值（符合 constraints），支持覆盖。
- **Spy 设计**：包装 EventPublisher，记录 Publish 调用，提供查询和断言方法。

## 约束
- 引擎选型与 _shared/test_infra.yaml 一致。
- Fixture 生成数据符合 fields.yaml 约束。

## 验收标准
- A1：TestSuite 可正确启动/停止引擎；Fixture 可生成合规数据。
- A7：配置与 test_infra.yaml 一致；Fixture 与 fields.yaml 一致。
