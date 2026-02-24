# L3 子特性：repository-interface-layering

## 功能说明
- **Repository 接口分层设计**：base → queryable → searchable → vector，按能力渐进组合。
- **Base Repository**：Save/FindByID/Delete 等核心 CRUD，所有存储适配器必须实现。
- **Queryable**：Find(filter)、Count(filter)，支持过滤条件查询。
- **Aggregatable**：聚合根语义，事务边界与乐观锁支持。
- **Searchable**：全文搜索，MongoDB text index / PostgreSQL tsvector。
- **VectorSearchable**：向量相似度查询，Atlas Vector Search / pgvector。

## 实现要点
- **接口定义**：Go interface 分层，Searchable 嵌入 Queryable，VectorSearchable 可独立或组合。
- **工厂设计**：RepositoryFactory 根据 EntityRegistry 的 storage_backend 和 capabilities 创建对应实现。
- **metadata 驱动**：storage.yaml 声明 storage_backend、indexes、vector_config，工厂据此选择适配器。

## 约束
- 业务代码仅依赖接口，不依赖具体适配器类型。
- 接口能力与 metadata 声明必须一致，未声明的能力不可暴露。

## 验收标准
- A1：接口分层清晰，可 mock 测试。
- A7：工厂由 metadata 驱动，无硬编码存储选择。
