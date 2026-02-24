# L2 特性：runtime-codegen

## 功能说明
- 从 metadata v3 模块化目录读取 aggregate/entity、fields、events、storage、service YAML。
- 通过 Go template 生成：Go struct、Repository interface、Repository impl（Mongo/PG）、Event struct、HTTP handler 骨架、OpenAPI schema、Migration 脚本（SQL/JS）、Dart DTO、契约测试骨架。
- 支持增量生成：仅生成变更实体的文件，不覆盖手写业务逻辑。

## 约束
- 生成代码必须 go build 编译通过。
- 生成代码中禁止包含硬编码存储地址或 secret。
- AI Agent 开发流程：修改 metadata → make codegen → 补充业务逻辑 → make test-contract。

## 验收标准
- A1：Post + UserProfile 两个聚合端到端 codegen → 编译 → 可用。
- A7：生成产物与 metadata YAML 100% 一致。
- A8：模板测试 + 生成代码编译测试。
