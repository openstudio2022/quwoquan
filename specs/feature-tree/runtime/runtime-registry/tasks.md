# 开发任务：runtime-registry

- [x] 设计：EntityRegistry 接口定义（GetEntity/GetFieldPolicy/GetCapabilities/GetStorageBackend/GetCacheTTL） → `runtime/registry/types.go`
- [x] 实现：v3 目录结构 YAML loader（遍历聚合/实体目录，解析 5 类 YAML） → `runtime/registry/loader.go`
- [x] 实现：内部一致性校验（字段引用、事件引用、存储映射） → `runtime/registry/loader.go`
- [x] 实现：运行时查询 API + 并发安全（GetAggregate/GetEntity/GetFieldPolicy/GetCapabilities/GetStorageBackend/GetCacheTTL/GetEnum/GetEvents/GetService/ListAggregates/ListEntities/Stats） → `runtime/registry/registry.go`
- [x] 测试：loader 单元测试（正常加载 + 错误路径 + 缺失文件） → `runtime/registry/registry_test.go`
- [x] 测试：query API 单元测试（全实体覆盖） → `runtime/registry/registry_test.go`
- [x] 测试：metadata 一致性 contract 测试 → `runtime/registry/registry_test.go`
- [x] gate：集成到 make verify + make gate
