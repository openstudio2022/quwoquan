# Design: Error & Permission Display Semantics

## 设计动因

端侧存在多处云端错误与权限提示，展示方式与文案不统一：
- 创作页提交失败用 SnackBar；附近位置加载失败用内联占位
- 相册权限拒绝与定位权限拒绝的提示形态各异
- 硬编码颜色、字号、间距

需建立跨域统一契约，与 Material Design / Apple HIG 最佳实践对齐。

## 关键决策

| 决策点 | 选项 A | 选项 B（选定） | 原因 |
|--------|--------|----------------|------|
| 阻塞性错误展示 | 仅 SnackBar | 内联占位（卡片式） | Material Design：关键错误须持久可见，SnackBar 易被忽略 |
| 权限永久拒绝 | 仅文案提示 | 文案 + 去设置按钮 | 业界惯例（高德/滴滴）：必须提供跳转设置的直接入口 |
| 规范落位 | 仅文档 | 特性树 L3 + Cursor 规则 | 可追溯、可验收、AI 可遵循 |

## 适用场景与约束

- **适用**：所有涉及云端请求（load/submit）或系统权限（location/photo/camera）的 Flutter 页面
- **不适用**：纯本地逻辑、无网络/权限依赖的页面
- **约束**：规范定义在 `specs/ux/error-and-permission-semantics.md`，本节点负责分解为可执行任务与验收

## 与现有系统关系

- **fullstack-error-behavior-contract**：提供 content 域错误码 codegen（ContentErrorCode、CloudErrorMapper）；本节点约束**展示方式**与 **token**，不扩展错误码定义
- **integration/location/errors.yaml**：位置域错误码；本节点约束位置错误在 UI 的展示形态
- **app-locale-infrastructure**：提供 context.l10n；本节点约定错误/权限相关 l10n key

## 未来演进

- 抽取共享 Widget：`CloudErrorInlinePlaceholder`、`PermissionDeniedCard`，减少各页面重复实现
- 扩展 INTEGRATION 域错误码 codegen（当前仅 CONTENT 有 ContentErrorCode），统一映射
