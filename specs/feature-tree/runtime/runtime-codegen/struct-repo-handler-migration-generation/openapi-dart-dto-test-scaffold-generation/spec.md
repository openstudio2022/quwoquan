# L5 横切：openapi-dart-dto-test-scaffold-generation

## 功能说明
- **OpenAPI 生成**：根据 service.yaml 的 API 定义生成 OpenAPI 3.0 schema，供 API 文档和客户端生成使用。
- **Dart DTO 生成**：根据 fields.yaml 生成 Dart 端 DTO 类，支持 JSON 序列化，供 Flutter 端调用 API 使用。
- **测试骨架生成**：生成 TestMain（启动测试引擎）、fixture.go（Fixture 工厂）、contract_test.go（契约测试骨架），与 runtime-testinfra 集成。

## 实现要点
- **OpenAPI 模板**：按 service.yaml 的 paths、request/response schema 生成，SECRET 字段不暴露。
- **Dart DTO 模板**：按 fields 生成 Dart class，含 fromJson/toJson，类型映射（string/int/bool/DateTime 等）。
- **测试骨架模板**：TestMain 调用 testutil 启动 PG/Mongo/Redis；fixture 使用 Builder 模式；contract_test 含基本 CRUD 断言骨架。

## 约束
- OpenAPI schema 与 service.yaml 完全一致。
- Dart DTO 与 fields.yaml 一致，SECRET 字段不生成。
- 测试骨架可编译运行，业务逻辑由开发者补充。

## 验收标准
- A7：OpenAPI、Dart DTO 与 metadata 一致。
- A8：契约测试骨架可编译运行，make test-contract 可执行。
