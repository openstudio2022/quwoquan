# L4 契约：cloud-network-error-display-contract

## 功能说明

云端/网络错误的统一展示契约：展示方式选择（内联 vs SnackBar）、语义 token、l10n key 约定。

## 范围

- 阻塞性错误（页面/列表首次加载失败）→ 内联占位，卡片式
- 次要错误（提交失败、单次操作失败）→ SnackBar floating
- Token：colorScheme.error、bodyMedium、AppSpacing.interGroup*
- l10n：loadFailed、submitFailed、networkUnavailable；domain 专属见 errors.yaml

## 与父节点关系

父节点：`error-permission-display-semantics` L3

## 验收标准

- 创作页提交失败使用 SnackBar
- 附近位置/发现流加载失败使用内联占位
- 所有错误文案来自 l10n，颜色/字号使用设计系统
- **L1a 错误码→l10n 映射契约**：CloudException.code 映射到正确 l10n 文案（替代纯 key 存在性断言）
- **L1b 位置选择页错误态**：注入 FakeLocationService 抛 CloudException 时，UI 展示正确内联错误
- **L1c 创作流**：选位置 → 云端超时 → 内联错误（非 SnackBar）
- **依赖**：L1b 错误态需 permission-card 的 LocationPermissionChecker（FakeChecker 返回 granted 以进入 nearby()）
