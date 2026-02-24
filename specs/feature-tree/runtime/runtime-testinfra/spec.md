# L2 特性：runtime-testinfra

## 功能说明
- 提供 TestSuite 基类，封装测试引擎（embedded-postgres / testcontainers-go MongoDB / miniredis）的启动/关闭。
- 提供 EventPublisher spy，捕获发布的领域事件用于断言。
- 提供 Fixture 工厂框架，从 fields.yaml 约束自动生成合规测试数据（Builder 模式）。
- codegen 生成 TestMain + fixture + contract_test 骨架。

## 约束
- 测试引擎选型必须与 _shared/test_infra.yaml 一致。
- 每个测试场景独立：Seed → Execute → Assert → Cleanup。
- 业务代码零修改，仅切换连接地址。

## 验收标准
- A1：三种测试引擎均可正常启动/运行/清理。
- A7：配置与 test_infra.yaml 一致，Fixture 与 fields.yaml 一致。
- A8：make test-contract 一键运行，CI 集成。
