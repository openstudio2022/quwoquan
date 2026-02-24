# L3 子特性：template-engine-and-metadata-reader

## 功能说明
- **Go Template Engine**：基于 text/template 或 html/template，支持自定义函数（如 snake_case、goType、nullable 等），按模板渲染生成代码。
- **Metadata Reader**：复用 registry loader 逻辑，从 metadata v3 目录读取指定聚合的 entity、fields、events、storage、service YAML，输出结构化数据供模板使用。
- **Template Registration**：建立模板名与模板文件的映射，支持按聚合类型选择不同模板（如 Mongo vs PG）。

## 实现要点
- **Engine Setup**：初始化 template.FuncMap，注册 snake_case、goType、nullable、plural 等辅助函数。
- **Metadata Reader Design**：调用 EntityRegistry Loader 或独立实现轻量 reader，输出 codegen 所需的 DTO 结构。
- **Template Registration**：按 entity/repository/events/handler/migration 等分类注册模板，支持 target 参数选择聚合。

## 约束
- Metadata Reader 必须与 contracts/metadata/ 结构完全一致。
- 模板渲染失败必须返回包含模板名、行号的错误。

## 验收标准
- A1：Engine 可正确渲染模板；Reader 可正确读取 metadata。
- A7：Reader 输出与 metadata YAML 完全一致；模板与 schema 对齐。
