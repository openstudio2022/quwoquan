# 开发任务：metadata-loader-and-entity-registry

- [ ] 设计：Loader 接口与 EntityRegistry 数据结构
- [ ] 实现：v3 目录遍历逻辑（按聚合/实体目录结构扫描）
- [ ] 实现：aggregate.yaml / entity.yaml 解析
- [ ] 实现：fields.yaml / events.yaml / storage.yaml / service.yaml 解析
- [ ] 实现：跨文件引用解析（aggregate → entity，entity → fields/events/storage）
- [ ] 实现：内部一致性校验（字段引用、事件引用、存储映射存在性）
- [ ] 实现：组装 EntityRegistry 内存结构
- [ ] 测试：Loader 单元测试（正常加载、错误路径、缺失文件、引用错误）
- [ ] 测试：metadata 一致性 contract 测试
- [ ] gate：集成到 make verify + make gate
