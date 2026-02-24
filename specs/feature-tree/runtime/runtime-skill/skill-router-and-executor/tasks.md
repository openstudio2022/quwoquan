# 开发任务：skill-router-and-executor

- [ ] 设计：SkillManifest 结构（对齐 skill_catalog.yaml）
- [ ] 实现：SkillRouter — 场景 + 标签 → Skill 匹配，优先级排序
- [ ] 实现：SkillExecutor — 上下文获取 → Tool 调用 → 结果返回
- [ ] 实现：SkillExecutor 超时控制（可配置，默认 2s）
- [ ] 实现：Skill 异常捕获与友好错误返回
- [ ] 测试：SkillRouter 单元测试（场景匹配 + 优先级）
- [ ] 测试：SkillExecutor 契约测试（端到端执行）
- [ ] gate：集成到 make gate
