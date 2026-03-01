# L3 子特性：page-layout-semantics

## 功能说明

端侧**页面布局**统一语义：顶部栏 leading（Modal 用 close、Stack 用 arrow_back）、内容区结构、底部栏（多选选择器 取消|完成）。与 `specs/ux/page-layout-semantics.md` 一一对应。

| L4 子节点 | 职责 |
|-----------|------|
| `top-toolbar-and-selection-pattern` | 顶部 leading 统一、选择器（单选 tap 即返回/多选 select-then-confirm） |
| `settings-page-structure` | 设置类页面统一使用 SettingsSemanticConstants、Section/Block 结构 |

## 范围

**适用**：创作、选择器、设置、聊天、资料管理等页面。  
**排除**：用户主页、作者主页、圈子主页（后续单独规范「主页设计」）。

## 与父/子节点关系

- 父节点：`runtime-client-foundation` L2
- 子节点：`top-toolbar-and-selection-pattern` L4、`settings-page-structure` L4

## 验收标准概要

- A1：Modal 页（创作、选择器）使用 close；Stack 页（设置、管理）使用 arrow_back
- A2：多选选择器底部固定「取消 | 完成」；单选 tap 即返回
- A3：设置类页面统一使用 SettingsSemanticConstants 与块结构
