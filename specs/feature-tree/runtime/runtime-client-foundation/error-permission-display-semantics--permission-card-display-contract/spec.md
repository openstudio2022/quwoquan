# L4 契约：permission-card-display-contract

## 功能说明

权限类（定位、相册、相机、麦克风）的统一展示契约：卡片形态、主操作（去设置）、l10n key、交互流程。

## 范围

- 权限卡片：图标 + 主文案 + 副文案 + 主操作按钮
- 永久拒绝 → 展示「去设置」；可再请求 → 引导重试或再次 request
- l10n：locationAppPermissionRequired、mediaPickerPermissionDenied、openSettings 等
- 地图/位置特定：加载态、权限态、云端错误态区分

## 与父节点关系

父节点：`error-permission-display-semantics` L3

## 验收标准

- 定位永久拒绝时展示「去设置」按钮
- 相册权限拒绝使用 mediaPickerPermissionDenied
- 卡片使用 AppSpacing、colorScheme token
- **LocationPermissionChecker 可注入**：支持测试注入 FakeChecker，便于 L1b 覆盖权限态
- **L4 Patrol（advisory）**：真机权限拒绝后展示「去设置」、点击可打开系统设置
