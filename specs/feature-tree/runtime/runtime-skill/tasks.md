# 开发任务：runtime-skill

- [x] 设计：SkillManifest 结构（对齐 skill_catalog.yaml） → `runtime/skill/types.go`
- [x] 设计：Tool 结构（对齐 tool_catalog.yaml） → `runtime/skill/types.go`
- [x] 实现：SkillRouter — 场景 + 标签 → Skill 匹配 → `runtime/skill/router.go`
- [x] 实现：SkillExecutor — 上下文获取 → Tool 调用 → 结果返回 → `runtime/skill/executor.go`
- [x] 实现：ToolProxy — Tool 注册 + 页面级发现 + DataClassMax 权限检查 → `runtime/skill/tool_registry.go`
- [x] 实现：ContextAuthorizer — 授权检查 + skill_consent 实体读写 → `runtime/skill/executor.go` (ConsentStore)
- [x] 实现：ToolRegistry — 注册 + 调用 + 页面级发现 → `runtime/skill/tool_registry.go`
- [ ] 实现：8 个内置 Skill 注册 → 依赖 assistant-service 业务层落地
- [x] 测试：SkillRouter 单元测试（场景匹配 + 优先级） → `runtime/skill/skill_test.go`
- [x] 测试：ContextAuthorizer 单元测试（授权/拒绝/DataClassMax） → `runtime/skill/skill_test.go`
- [x] 测试：Skill 执行（超时 + consent + DataClass） → `runtime/skill/skill_test.go`
- [x] gate：go vet + go test 全量通过
