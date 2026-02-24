# L2 特性：runtime-repository

## 功能说明
- 提供 Repository/Queryable/Aggregatable/Searchable/VectorSearchable 分层接口。
- MongoDB 适配器：从 EntityRegistry 获取集合名、索引，支持 CRUD + 全文搜索。
- PostgreSQL 适配器：从 EntityRegistry 获取表名、列映射，支持 CRUD + 事务 + 乐观锁。
- Redis 缓存中间件：缓存读取 → 未命中回源 → 写缓存，TTL 从 metadata 获取。
- 向量搜索适配器：Atlas Vector Search / pgvector 相似度查询。
- 存储工厂：根据 metadata 的 storage_backend 自动路由创建 Repository 实例。

## 约束
- 业务服务禁止直接操作数据库驱动，必须通过 Repository 接口。
- 缓存 TTL 由 metadata aggregate.yaml 的 cache_ttl_seconds 决定。
- 事务范围限定在同一 Aggregate 内。

## 验收标准
- A1：Post（MongoDB）和 UserProfile（PostgreSQL）端到端 CRUD 全通过。
- A3：连接池、慢查询日志可配置。
- A7：存储路由完全由 metadata 驱动，无硬编码。
- A8：Mongo/PG/Cache 适配器均有真实数据库契约测试。
