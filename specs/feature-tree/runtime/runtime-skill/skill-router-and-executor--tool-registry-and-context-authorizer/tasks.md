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

## Folded legacy node `skill-store-and-ecosystem`

# 开发任务：skill-store-and-ecosystem

- [ ] 设计：Skill Store 数据模型（Skill 版本/状态/评分/审核记录）
- [ ] 实现：Skill 注册 + 发布 API
- [ ] 实现：Skill 审核工作流
- [ ] 实现：Skill 灰度发布 + 效果评估 + 自动择优
- [ ] 实现：沙箱执行环境（资源隔离 + 超时控制）
- [ ] 实现：用户端 Skill 发现 + 安装 + 授权管理
- [ ] 测试：Skill Store 集成测试（注册→审核→发布→安装）
- [ ] 测试：沙箱隔离安全测试
- [ ] gate：集成到 make gate

## 当前交付任务
- [ ] Migrated legacy node: `skill-store-and-ecosystem` (from `runtime/runtime-skill/skill-router-and-executor/tool-registry-and-context-authorizer/skill-store-and-ecosystem`)
