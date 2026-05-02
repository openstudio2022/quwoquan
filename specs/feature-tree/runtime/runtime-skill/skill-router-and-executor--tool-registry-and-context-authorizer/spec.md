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

## Folded current node `skill-store-and-ecosystem`

# L5 横切能力：skill-store-and-ecosystem

## 功能说明
- Skill Store 管理服务：Skill 注册/发布/版本管理/审核/评分。
- 沙箱执行环境：Ecosystem Skill 资源隔离。
- 用户端 Skill 发现 + 安装 + 授权管理界面。
- Skill 版本灰度 + 效果评估 + 自动择优。

## 约束
- Ecosystem Skill 必须在沙箱中执行，不得直接访问生产数据库。
- Skill 发布必须经过审核。

## 验收标准
- A1：Skill 注册 → 审核 → 灰度发布 → 用户安装 → 使用。
- A3：沙箱隔离 + 灰度 + 效果评估。
- A5：运营管理全流程。
- A6：安全隔离 + 数据不泄露。
