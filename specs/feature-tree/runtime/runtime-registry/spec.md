# L2 特性：runtime-registry

## 功能说明
- 从 metadata v3 模块化目录结构加载全部 YAML（aggregate.yaml/entity.yaml + fields.yaml + events.yaml + storage.yaml + service.yaml）。
- 提供运行时查询 API：GetEntity, GetFieldPolicy, GetCapabilities, GetStorageBackend, GetCacheTTL, GetTagTaxonomy。
- Repository 框架和拦截链依赖 EntityRegistry 获取实体元信息。

## 约束
- 未在 metadata 注册的实体不允许通过 Repository 读写。
- 加载时校验 metadata 内部一致性（字段引用、事件引用、存储映射）。

## 验收标准
- A1：全部 12 个聚合/实体的 metadata 可正确加载，查询 API 返回一致结果。
- A7：Registry 数据与 contracts/metadata/ YAML 文件内容完全一致。
- A8：loader + query API 单元测试 + metadata 一致性 contract 测试。
