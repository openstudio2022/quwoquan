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
