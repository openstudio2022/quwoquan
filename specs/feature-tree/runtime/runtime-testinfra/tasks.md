# 开发任务：runtime-testinfra

- [x] 实现：Suite — embedded-postgres 启动/关闭/migration/truncate → `runtime/testinfra/testinfra.go`
- [x] 实现：Suite — testcontainers-go/mongodb 启动/关闭/索引/cleanup → `runtime/testinfra/testinfra.go`
- [x] 实现：Suite — miniredis 启动/关闭/flush/时间控制 → `runtime/testinfra/testinfra.go`
- [x] 实现：EventSpy — EventPublisher spy（捕获 + AssertPublished） → `runtime/testinfra/testinfra.go`
- [x] 实现：MiniRedisCache — Redis 缓存测试辅助 → `runtime/testinfra/testinfra.go`
- [x] 实现：CleanPG/CleanMongo/CleanRedis/CleanAll 清理方法 → `runtime/testinfra/testinfra.go`
- [x] 集成：codegen 模板生成 TestMain + fixture + contract_test → `runtime/codegen/`
- [x] 测试：三种引擎的启动/CRUD/清理自测 → `runtime/testinfra/testinfra_test.go`
- [x] 测试：EventSpy 捕获 + 断言自测 → `runtime/testinfra/testinfra_test.go`
- [x] gate：make test-contract 命令 + CI 集成
