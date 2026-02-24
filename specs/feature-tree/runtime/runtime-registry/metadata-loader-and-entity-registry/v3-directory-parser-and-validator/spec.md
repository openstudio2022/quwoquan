# L4 对象任务：v3-directory-parser-and-validator

## 功能说明
- **Parser**：解析 v3 目录下的 YAML 文件（aggregate.yaml、entity.yaml、fields.yaml、events.yaml、storage.yaml、service.yaml），输出结构化 Go 对象。
- **Validator**：校验 metadata 内部一致性，包括字段引用、事件引用、存储映射的存在性与正确性。

## 实现要点
- **YAML 解析**：使用标准 YAML 库解析，支持 v3 schema 约定（字段名、类型、嵌套结构）。
- **Schema 校验**：校验必填字段、类型、枚举值，非法 schema 返回明确错误。
- **跨文件引用检查**：entity 引用的 fields/events/storage 必须在对应 YAML 中存在；字段引用、事件引用、存储映射必须可解析。

## 约束
- 解析失败必须返回包含文件路径、行号、字段名的错误。
- 校验失败必须阻止加载完成，不静默忽略。

## 验收标准
- A7：Parser 输出与 contracts/metadata/ YAML 完全一致；Validator 覆盖全部引用类型。
- A8：Parser + Validator 单元测试，metadata 一致性 contract 测试。
