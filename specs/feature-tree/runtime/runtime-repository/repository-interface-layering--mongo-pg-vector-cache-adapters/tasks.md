# 开发任务：mongo-pg-vector-cache-adapters

- [ ] 实现：MongoDB 适配器 Save/FindByID/Find/Count/Search/Delete
- [ ] 实现：MongoDB 从 EntityRegistry 获取集合名、索引
- [ ] 实现：PostgreSQL 适配器 Save/FindByID/Find/Count/Delete
- [ ] 实现：PostgreSQL 事务与乐观锁（version 列）
- [ ] 实现：PostgreSQL 从 EntityRegistry 获取表名、列映射
- [ ] 实现：Redis 缓存中间件（读缓存/写透/写失效）
- [ ] 实现：Redis TTL 从 metadata cache_ttl_seconds 获取
- [ ] 实现：向量搜索适配器（Atlas Vector Search / pgvector）
- [ ] 测试：MongoDB 适配器契约测试（testcontainers）
- [ ] 测试：PostgreSQL 适配器契约测试（embedded-postgres）
- [ ] 测试：Redis 缓存中间件契约测试（miniredis）
- [ ] gate：集成到 make test-contract + make gate

## Folded legacy node `storage-routing-and-interceptor-chain`

# 开发任务：storage-routing-and-interceptor-chain

- [ ] 实现：RepositoryFactory 根据 EntityRegistry.GetStorageBackend 路由
- [ ] 实现：缓存叠加逻辑（cache_enabled 时包装 Redis 中间件）
- [ ] 实现：Repository 拦截链（span、metric、慢查询、超时）
- [ ] 集成：runtime-config 连接池、慢查询阈值、超时配置
- [ ] 集成：runtime-observability OTEL span/metric 绑定
- [ ] 测试：存储工厂路由正确性测试（各 storage_backend 组合）
- [ ] 测试：拦截链集成测试（span、metric、慢查询）
- [ ] gate：集成到 make test-contract + make gate

## 当前交付任务
- [ ] Migrated legacy node: `storage-routing-and-interceptor-chain` (from `runtime/runtime-repository/repository-interface-layering/mongo-pg-vector-cache-adapters/storage-routing-and-interceptor-chain`)
