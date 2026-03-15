# [场景名] 设计与约束模板

> **从属**：`../PERSONAL_ASSISTANT_DESIGN_AND_CONSTRAINTS.md`

## 1. 场景边界与目标

- 本场景解决什么问题
- 明确不做什么
- 影响哪些层：runtime / skill / tool / prompt / UI

## 2. 设计原则与流程

- 先说明本场景应优先改 asset、metadata 还是 runtime
- 说明运行时如何消费新增内容
- 说明与三类核心文档的映射

## 3. 实现约束

- 本场景禁止哪些硬编码
- 本场景的唯一真相源在哪里
- 允许哪些兼容逻辑，退出条件是什么

## 4. 验收与门禁

- 需要哪些 contract test / regression test
- 需要做哪些字符串治理与垂类特判审计
- 需要验证哪些文档引用与回滚条件

## 5. 相关主文档章节索引

- `PERSONAL_ASSISTANT_ARCHITECTURE_AND_FLOW.md`
- `PERSONAL_ASSISTANT_SKILL_AND_TOOL_EXTENSIBILITY.md`
- `PERSONAL_ASSISTANT_DESIGN_AND_CONSTRAINTS.md`
