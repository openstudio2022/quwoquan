# 开发任务：runtime-repository

- [x] 设计：Repository[T] 泛型接口定义（Save/FindByID/Find/Count/Delete） → `runtime/repository/repository.go`
- [x] 实现：MongoDB 适配器（Save/FindByID/Find/Count/Delete） → `runtime/repository/mongo_adapter.go`
- [x] 实现：PostgreSQL 适配器（Save/FindByID/Find/Count/Delete + 事务 + 乐观锁） → `runtime/repository/pg_adapter.go`
- [x] 实现：Redis 缓存中间件（读缓存 read-through + 写失效 invalidation + TTL 驱动） → `runtime/repository/cached.go`
- [x] 实现：Unit of Work / 事务管理 → `runtime/repository/uow.go`
- [x] 实现：存储工厂（根据 EntityRegistry 自动路由，auto-wrap cache when TTL > 0，auto-wrap interceptors） → `runtime/repository/factory.go`
- [x] 测试：MongoDB 适配器契约测试（testcontainers） → `runtime/repository/repository_test.go`
- [x] 测试：PostgreSQL 适配器契约测试（embedded-postgres） → `runtime/repository/repository_test.go`
- [x] 测试：Redis 缓存中间件契约测试（miniredis） → `runtime/repository/repository_test.go`
- [x] 测试：存储工厂路由正确性测试 → `runtime/repository/repository_test.go`
- [x] gate：集成到 make test-contract + make gate
