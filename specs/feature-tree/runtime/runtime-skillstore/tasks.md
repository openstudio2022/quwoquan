# 开发任务：runtime-skillstore

- [x] 设计：SkillRegistration + ReviewRecord + GrayConfig + SandboxConfig 类型 → `runtime/skillstore/types.go`
- [x] 实现：Store（MongoDB）— 注册/查询/列表/状态转换 → `runtime/skillstore/store.go`
- [x] 实现：状态机（validTransitions 有限状态机 + isValidTransition） → `runtime/skillstore/store.go`
- [x] 实现：SubmitReview — 自动检查 + 人工审核 → `runtime/skillstore/store.go`
- [x] 实现：SetGrayConfig — 灰度发布配置 → `runtime/skillstore/store.go`
- [x] 实现：UpdateMetrics — 指标采集 → `runtime/skillstore/store.go`
- [x] 实现：自动检查（context_scope / tool_dependencies / data_class_policy） → `runAutoChecks()`
- [x] 实现：SandboxConfig 资源约束定义 → `runtime/skillstore/types.go`
- [x] 测试：17 种状态转换覆盖（合法/非法） → `runtime/skillstore/skillstore_test.go`
- [x] 测试：自动检查场景（internal pass / ecosystem sensitive fail / excessive context） → test
- [x] gate：go vet + go test 全量通过
