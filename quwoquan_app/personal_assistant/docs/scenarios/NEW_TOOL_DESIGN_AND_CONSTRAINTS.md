# 新增 Tool 设计与约束

> **从属**：`../PERSONAL_ASSISTANT_DESIGN_AND_CONSTRAINTS.md`

## 1. 适用场景

当新增工具、修改工具合同、调整工具权限或把文案从 runtime 迁到工具 metadata 时，必须阅读本文。

## 2. 正确落点

新增 tool 的主要变更应落在：

- `lib/personal_assistant/tools/`
- `lib/personal_assistant/tools/tool_registry.dart`
- `assets/personal_assistant/tools/catalog/tool_catalog.meta.json`
- `assets/personal_assistant/tools/catalog/tool_permissions.json`

## 3. 设计约束

- 禁止在工具实现中写 domain 特判
- 禁止在 runtime 其他位置复制一套工具标题、phase 文案、完成文案
- 禁止把展示字段当成行为键
- 需要用户确认的工具必须通过统一确认策略和权限配置表达

## 4. 验收要点

- 参数与输出满足工具合同
- tool metadata、权限矩阵与实现保持一致
- trace / user event 文案来自 metadata
- 相关 contract test、registry test 和回归测试通过
