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
