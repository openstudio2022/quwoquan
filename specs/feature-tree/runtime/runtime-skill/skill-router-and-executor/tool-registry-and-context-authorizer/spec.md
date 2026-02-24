# L4 对象任务：tool-registry-and-context-authorizer

## 功能说明
- ToolRegistry：从 tool_catalog.yaml 加载 Tool 定义，支持页面级 Tool 发现。
- ToolProxy：代理 Skill 对 Tool 的调用，执行 DataClassMax 权限检查。
- ContextAuthorizer：基于 skill_consent 实体管理 Skill 的上下文访问授权。

## 约束
- DataClassMax 不可绕过，Skill 可访问数据的分类级别严格受控。
- 授权记录持久化到 skill_consent 实体（PostgreSQL）。

## 验收标准
- A1：Tool 注册 + 发现 + 代理调用端到端可用。
- A6：DataClassMax 权限拒绝 + 授权流程正确。
- A8：权限和授权全路径单元测试。
