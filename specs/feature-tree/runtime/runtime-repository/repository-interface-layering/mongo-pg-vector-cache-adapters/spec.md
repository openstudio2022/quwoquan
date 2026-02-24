# L4 对象任务：mongo-pg-vector-cache-adapters

## 功能说明
- **MongoDB 适配器**：从 EntityRegistry 获取集合名、索引定义，实现 Save/FindByID/Find/Count/Search/Delete。支持全文搜索（text index）。
- **PostgreSQL 适配器**：从 EntityRegistry 获取表名、列映射，实现 CRUD + 事务 + 乐观锁（version 字段）。
- **Redis 缓存中间件**：包装任意 Repository，实现读缓存 → 未命中回源 → 写缓存，TTL 从 aggregate.yaml cache_ttl_seconds 获取，支持写失效。
- **向量搜索适配器**：Atlas Vector Search（MongoDB）或 pgvector（PostgreSQL），根据 metadata vector_config 配置相似度查询。

## 实现要点
- **MongoDB**：使用官方 driver，集合名 = entity 名或 storage.yaml 指定，索引按 metadata 创建。
- **PostgreSQL**：使用 pgx，表名/列名由 storage.yaml 映射，乐观锁通过 version 列实现。
- **Redis**：使用 go-redis，key 格式 `{aggregate}:{entity}:{id}`，TTL 可配置。
- **向量搜索**：Atlas Vector Search 需配置 index，pgvector 需 extension 和 embedding 列。

## 约束
- 适配器不直接依赖业务类型，通过泛型或反射从 EntityRegistry 获取 schema。
- 契约测试使用真实引擎（testcontainers/embedded-postgres/miniredis），不 mock。

## 验收标准
- A1：四种适配器 CRUD/缓存/向量搜索端到端正确。
- A8：Mongo/PG/Cache 均有真实数据库契约测试。
