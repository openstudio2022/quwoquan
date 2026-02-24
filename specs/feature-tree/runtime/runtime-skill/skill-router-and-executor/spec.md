# L3 子特性：skill-router-and-executor

## 功能说明
- **SkillRouter**：根据 PageContext 的 scene_type、snapshot 标签（如 tag=travel）→ 匹配适用的 Skill；支持优先级；返回 SkillManifest。
- **SkillExecutor**：执行 Skill 流程：获取上下文（ContextAssembler）→ 解析 Skill 步骤 → 调用 Tool → 返回结果；超时控制。
- **匹配规则**：skill_catalog.yaml 定义每个 Skill 的 scene_types、tags、priority。

## 实现要点
- **SkillRouter**：加载 skill_catalog；按 scene_type 过滤 → 按 tags 匹配 → 按 priority 排序 → 返回首个。
- **SkillExecutor**：接收 skillId、userId、PageContext；调用 ContextAuthorizer 检查授权；调用 ContextAssembler 获取上下文；按 Skill 步骤调用 Tool；超时控制（如 2s）。

## 约束
- Skill 执行有超时控制。
- Skill 异常不影响主路径（捕获并返回友好错误）。
- 与 skill_catalog.yaml 一致。

## 验收标准
- A1：SkillRouter 匹配 + SkillExecutor 执行端到端正确。
- A3：超时控制 + 异常隔离。
- A8：SkillRouter 单元测试 + SkillExecutor 契约测试。
