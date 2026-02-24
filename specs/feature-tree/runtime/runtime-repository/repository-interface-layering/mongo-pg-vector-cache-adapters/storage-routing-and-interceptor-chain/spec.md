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
