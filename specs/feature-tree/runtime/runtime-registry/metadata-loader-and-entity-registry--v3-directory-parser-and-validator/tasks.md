# 开发任务：v3-directory-parser-and-validator

- [ ] 设计：v3 YAML schema 定义（aggregate/entity/fields/events/storage/service）
- [ ] 实现：aggregate.yaml / entity.yaml Parser
- [ ] 实现：fields.yaml / events.yaml / storage.yaml / service.yaml Parser
- [ ] 实现：schema 校验（必填字段、类型、枚举）
- [ ] 实现：跨文件引用 Validator（字段引用、事件引用、存储映射）
- [ ] 实现：错误信息格式化（文件路径、行号、字段名）
- [ ] 测试：Parser 单元测试（正常解析、非法 schema、缺失字段）
- [ ] 测试：Validator 单元测试（引用正确、引用错误、循环引用）
- [ ] 测试：metadata 一致性 contract 测试
- [ ] gate：集成到 make verify + make gate

## Folded legacy node `runtime-query-api-and-hot-reload`

# 开发任务：runtime-query-api-and-hot-reload

- [ ] 设计：EntityRegistry 查询接口（GetEntity/GetFieldPolicy/GetCapabilities/GetStorageBackend/GetCacheTTL/GetTagTaxonomy）
- [ ] 实现：查询 API 实现 + 未注册实体错误处理
- [ ] 实现：并发安全（RWMutex 或 copy-on-write）
- [ ] 实现：Hot-reload 文件变更检测（fsnotify 或轮询）
- [ ] 实现：Hot-reload 重新加载 + 校验 + 原子替换
- [ ] 实现：Hot-reload 配置开关与灰度支持
- [ ] 实现：加载完成日志（entity 总数、字段总数）
- [ ] 实现：Hot-reload 变更摘要日志
- [ ] 测试：Query API 单元测试（全实体覆盖、未注册实体）
- [ ] 测试：Hot-reload 单元测试（更新、回滚、并发）
- [ ] gate：集成到 make verify + make gate

## 当前交付任务
- [ ] Migrated legacy node: `runtime-query-api-and-hot-reload` (from `runtime/runtime-registry/metadata-loader-and-entity-registry/v3-directory-parser-and-validator/runtime-query-api-and-hot-reload`)
