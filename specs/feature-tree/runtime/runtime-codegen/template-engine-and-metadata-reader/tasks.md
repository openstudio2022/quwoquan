# 开发任务：template-engine-and-metadata-reader

- [ ] 设计：TemplateEngine 接口（Render(templateName, data) → []byte）
- [ ] 设计：MetadataReader 接口（Read(target string) → CodegenMetadata）
- [ ] 实现：Go template FuncMap（snake_case, goType, nullable, plural 等）
- [ ] 实现：MetadataReader 复用 registry loader 或独立实现
- [ ] 实现：CodegenMetadata DTO 结构（与 metadata v3 schema 对齐）
- [ ] 实现：模板注册表（template name → file path）
- [ ] 实现：按 target 聚合选择模板逻辑
- [ ] 测试：MetadataReader 单元测试（正常/异常/缺失文件）
- [ ] 测试：TemplateEngine 单元测试（渲染正确性、FuncMap）
- [ ] gate：集成到 make verify + make gate
