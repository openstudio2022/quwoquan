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

## Folded current node `storage-routing-and-interceptor-chain`

# L5 横切：storage-routing-and-interceptor-chain

## 功能说明
- **存储路由策略**：RepositoryFactory 根据 EntityRegistry.GetStorageBackend(aggregate, entity) 自动选择 MongoDB/PostgreSQL 适配器，并叠加 Redis 缓存（若 metadata 声明 cache_enabled）。
- **拦截链集成点**：Repository 操作（Save/FindByID/Find/Delete）经过拦截链，支持观测、慢查询、治理策略。
- **观测集成**：OTEL span、延迟 metric、慢查询日志由拦截链统一注入，Repository 适配器不感知。

## 实现要点
- **路由逻辑**：Factory 读取 EntityRegistry 的 storage_backend、cache_enabled、cache_ttl_seconds，按配置组装适配器链。
- **拦截链**：Repository 接口包装一层 Middleware，支持 span、metric、慢查询、超时等横切逻辑。
- **runtime-config 集成**：连接池大小、慢查询阈值、超时从 runtime-config 读取。

## 约束
- 存储选择禁止硬编码，必须由 metadata 驱动。
- 拦截链与 runtime-observability、runtime-governance 对齐，不重复实现。

## 验收标准
- A3：连接池、慢查询、超时可配置。
- A4：Repository 操作自动产生 span、metric、慢查询日志。
- A7：存储路由完全由 metadata 驱动。
