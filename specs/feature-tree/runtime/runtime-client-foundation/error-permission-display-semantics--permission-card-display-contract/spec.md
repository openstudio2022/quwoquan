# L4 契约：permission-card-display-contract

## 功能说明

权限类（定位、相册、相机、麦克风）的统一展示契约：卡片形态、主操作（去设置）、l10n key、交互流程，并作为统一 `AppInlineGateState` / `AppPageErrorState` 的第一类可复用 gate 场景。

## 范围

- 权限卡片：图标 + 主文案 + 副文案 + 主操作按钮
- 永久拒绝 → 展示「去设置」；可再请求 → 引导重试或再次 request
- **统一协调层**：`AppPermissionCoordinator` + `AppPermissionSurface`（`jit` / `page`）
- **L0–L4 漏斗**与 `suppressSettingsPrompt` 防死循环（见 `specs/ux/error-and-permission-semantics.md` §2.8–§2.9）
- l10n：`permissionSettingsGateTitle`、`permissionPrimerContinue`、`chatVoicePendingRetry` 等
- gate 语义：权限被拒绝时说明“当前为什么不能继续”以及“继续所需动作”

## 与父节点关系

父节点：`error-permission-display-semantics` L3

## 验收标准

- 定位永久拒绝时展示「去设置」按钮
- 相册权限拒绝使用 mediaPickerPermissionDenied
- 卡片使用 AppSpacing、colorScheme token
- **LocationPermissionChecker 可注入**：支持测试注入 FakeChecker，便于 `local_contract` 覆盖权限态
- **统一 gate 载体**：权限态与登录门禁态共享 `AppInlineGateState` 结构，但图标、按钮和副说明由权限语义决定
- **user_acceptance Patrol（advisory）**：真机权限拒绝后展示「去设置」、点击可打开系统设置
