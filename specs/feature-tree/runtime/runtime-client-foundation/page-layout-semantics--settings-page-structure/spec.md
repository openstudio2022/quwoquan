# L4 契约：settings-page-structure

## 功能说明

设置类页面统一使用 SettingsSemanticConstants，块结构（blockBackground、blockBorderRadius、sectionVerticalPadding 等），设置行最小高度、分割线、块间距一致。

## 范围

- SettingsPage、DeveloperSettingsPage、ChatSettingsPage、AssistantManagementPage
- 建议抽取 SettingsSection、SettingsRow 等可复用组件

## 与父节点关系

父节点：`page-layout-semantics` L3

## 验收标准

- 设置类页面使用 SettingsSemanticConstants
- 块/行视觉与交互一致
