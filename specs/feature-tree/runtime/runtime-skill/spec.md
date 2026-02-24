# L2 特性：runtime-skill

## 功能说明
- SkillRouter：根据 PageContext 场景 + 标签 → 匹配适用的 Skill。
- SkillExecutor：执行 Skill（获取上下文 → 调用 Tool → 返回结果）。
- ToolProxy：Tool 注册 + 页面级 Tool 发现 + 权限代理。
- ContextAuthorizer：首次触发需用户授权，二次直接执行（基于 skill_consent 实体）。
- ToolRegistry：从 tool_catalog.yaml 加载 Tool 定义。

## 约束
- Skill 访问上下文需用户授权（基于 skill_consent 实体）。
- DataClassMax 约束 Skill 可访问的数据分类级别。
- Skill 执行有超时控制。

## 验收标准
- A1：SkillRouter 匹配 + Skill 执行 + Tool 调用端到端可用。
- A6：授权机制 + DataClassMax 约束。
- A7：与 skill_catalog/tool_catalog/skill_consent metadata 一致。
- A8：全组件自动化测试。
