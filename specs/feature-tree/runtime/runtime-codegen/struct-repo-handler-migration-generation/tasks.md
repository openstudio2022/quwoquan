# 开发任务：struct-repo-handler-migration-generation

- [ ] 实现：entity.go.tmpl（Go struct + JSON/validation tags）
- [ ] 实现：repository.go.tmpl（Repository interface）
- [ ] 实现：repo_impl_mongo.go.tmpl（MongoDB 实现）
- [ ] 实现：repo_impl_pg.go.tmpl（PostgreSQL 实现）
- [ ] 实现：events.go.tmpl（Event struct）
- [ ] 实现：http_handler.go.tmpl（HTTP handler 骨架）
- [ ] 实现：migration_pg.sql.tmpl（PostgreSQL DDL）
- [ ] 实现：migration_mongo.js.tmpl（MongoDB 索引脚本）
- [ ] 测试：entity 模板单元测试
- [ ] 测试：repo 模板单元测试
- [ ] 测试：handler 模板单元测试
- [ ] 测试：migration 模板单元测试
- [ ] 测试：Post + UserProfile 生成代码 go build
- [ ] gate：集成到 make codegen + make gate
