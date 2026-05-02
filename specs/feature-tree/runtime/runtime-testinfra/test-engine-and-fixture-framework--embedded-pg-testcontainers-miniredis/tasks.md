# 开发任务：embedded-pg-testcontainers-miniredis

- [ ] 实现：pg_suite.go — embedded-postgres 启动/关闭
- [ ] 实现：pg_suite — migration 执行
- [ ] 实现：pg_suite — truncate 清理
- [ ] 实现：mongo_suite.go — testcontainers mongo 启动/关闭
- [ ] 实现：mongo_suite — 索引创建
- [ ] 实现：mongo_suite — cleanup
- [ ] 实现：redis_suite.go — miniredis 启动/关闭
- [ ] 实现：redis_suite — flush/时间控制
- [ ] 实现：event_spy.go — EventPublisher spy
- [ ] 测试：pg_suite 自测（启动/CRUD/清理）
- [ ] 测试：mongo_suite 自测（启动/CRUD/清理）
- [ ] 测试：redis_suite 自测（SET/GET/TTL）
- [ ] 测试：event_spy 自测（捕获/断言）
- [ ] gate：集成到 make gate

## Folded current node `codegen-test-and-ci-integration`

# 开发任务：codegen-test-and-ci-integration

- [ ] 集成：codegen testmain.go.tmpl 调用 testutil 引擎
- [ ] 集成：codegen fixture.go.tmpl 使用 testutil.Fixture
- [ ] 集成：codegen contract_test.go.tmpl 含 CRUD 断言骨架
- [ ] 实现：make test-contract 命令（遍历契约测试）
- [ ] 实现：CI 配置（PR 时运行 make test-contract）
- [ ] 测试：Post + UserProfile 契约测试端到端
- [ ] gate：make test-contract 集成到 make gate

## 当前交付任务
- [ ] Migrated current node: `codegen-test-and-ci-integration` (from `runtime/runtime-testinfra/test-engine-and-fixture-framework/embedded-pg-testcontainers-miniredis/codegen-test-and-ci-integration`)
