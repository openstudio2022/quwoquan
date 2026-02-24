# 开发任务：tool-registry-and-context-authorizer

- [ ] 实现：ToolRegistry — 从 tool_catalog.yaml 加载 Tool 定义
- [ ] 实现：ToolRegistry — 页面级 Tool 发现（根据 PageContext 类型筛选可用 Tool）
- [ ] 实现：ToolProxy — 代理 Skill 对 Tool 的调用
- [ ] 实现：ToolProxy — DataClassMax 权限检查（Skill 级别 vs Tool 级别）
- [ ] 实现：ContextAuthorizer — 授权检查（查询 skill_consent 实体）
- [ ] 实现：ContextAuthorizer — 首次授权提示 + 授权记录写入
- [ ] 测试：ToolProxy 权限检查单元测试（允许/拒绝场景）
- [ ] 测试：ContextAuthorizer 授权流程单元测试
- [ ] gate：集成到 make gate
