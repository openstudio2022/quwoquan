# 开发任务：runtime-codegen

- [x] 设计：codegen CLI 参数（target 聚合名/all, output 目录, force 覆盖模式） → `runtime/codegen/codegen.go`
- [x] 实现：metadata v3 目录 reader（复用 registry loader 逻辑） → `runtime/codegen/codegen.go`
- [x] 实现：Go model generation（entity struct 生成） → `runtime/codegen/codegen.go`
- [x] 实现：template rendering（模板渲染引擎） → `runtime/codegen/codegen.go`
- [x] 实现：multi-aggregate support（多聚合批量生成） → `runtime/codegen/codegen.go`
- [x] 实现：entity.go.tmpl → Go struct → `runtime/codegen/templates/`
- [x] 实现：repository.go.tmpl → Repository interface → `runtime/codegen/templates/`
- [x] 实现：events.go.tmpl → Event struct → `runtime/codegen/templates/`
- [x] 实现：http_handler.go.tmpl → HTTP handler 骨架 → `runtime/codegen/templates/`
- [x] 实现：migration 模板 → DDL/索引脚本 → `runtime/codegen/templates/`
- [x] 实现：test 骨架模板（testmain + fixture + contract_test） → `runtime/codegen/templates/`
- [x] 测试：模板单元测试（验证生成产物正确性） → `runtime/codegen/codegen_test.go`
- [x] 测试：Post + UserProfile 端到端 codegen → go build → `runtime/codegen/codegen_test.go`
- [x] gate：make codegen 命令 + 集成到 make gate
