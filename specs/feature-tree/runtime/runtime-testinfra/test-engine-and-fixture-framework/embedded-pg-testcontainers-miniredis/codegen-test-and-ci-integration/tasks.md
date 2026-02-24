# 开发任务：codegen-test-and-ci-integration

- [ ] 集成：codegen testmain.go.tmpl 调用 testutil 引擎
- [ ] 集成：codegen fixture.go.tmpl 使用 testutil.Fixture
- [ ] 集成：codegen contract_test.go.tmpl 含 CRUD 断言骨架
- [ ] 实现：make test-contract 命令（遍历契约测试）
- [ ] 实现：CI 配置（PR 时运行 make test-contract）
- [ ] 测试：Post + UserProfile 契约测试端到端
- [ ] gate：make test-contract 集成到 make gate
