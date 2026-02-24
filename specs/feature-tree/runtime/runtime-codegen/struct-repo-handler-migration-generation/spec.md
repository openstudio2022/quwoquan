# L4 对象任务：struct-repo-handler-migration-generation

## 功能说明
- **entity.go.tmpl**：根据 fields.yaml 生成 Go struct，包含 JSON tag、validation tag。
- **repository.go.tmpl**：生成 Repository interface（FindByID、Save、Delete 等）。
- **repo_impl_mongo.go.tmpl**：生成 MongoDB Repository 实现。
- **repo_impl_pg.go.tmpl**：生成 PostgreSQL Repository 实现。
- **events.go.tmpl**：根据 events.yaml 生成 Event struct。
- **http_handler.go.tmpl**：生成 HTTP handler 骨架（CRUD 路由绑定）。
- **migration_pg.sql.tmpl**：生成 PostgreSQL DDL（CREATE TABLE、INDEX）。
- **migration_mongo.js.tmpl**：生成 MongoDB 索引脚本。

## 实现要点
- **Struct 生成**：遍历 fields，按类型映射生成 Go 类型，支持 nullable、constraints。
- **Repository 生成**：按 storage.yaml 选择 Mongo/PG 模板。
- **Handler 生成**：按 service.yaml 的 API 定义生成路由和 handler 骨架。
- **Migration 生成**：按 fields 和 storage 配置生成 DDL/索引脚本。

## 约束
- 生成代码必须 go build 通过。
- 字段名、类型与 fields.yaml 100% 一致。

## 验收标准
- A1：Post + UserProfile 端到端生成 → 编译通过。
- A8：各模板单元测试 + 生成代码编译测试。
