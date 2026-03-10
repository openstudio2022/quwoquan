# Design: Permission Card Display Contract

## 设计动因

规范 `specs/ux/error-and-permission-semantics.md` §2 的落地实现。

## 关键决策

永久拒绝必须提供「去设置」主操作；调用 Geolocator.openAppSettings() 或 openLocationSettings()。

## 适用场景与约束

适用：定位、相册、相机、麦克风等系统权限。不适用：应用内功能开关。

## LocationPermissionChecker 抽取（测试可测性）

**动因**：`CreateLocationService.ensureLocationPermission()` 为 static，直接调用 Geolocator，导致 L1b 无法覆盖权限态（test 环境下 Geolocator 通常返回 denied）。

**设计**：
- 抽取接口 `LocationPermissionChecker`：`Future<PermissionResult> checkAndRequest()`
- 默认实现调用 Geolocator，返回 `{result: granted|needApproval|permanentlyDenied, position?}`
- 页面 / CreateLocationService 注入；测试注入 `FakeChecker` 返回 granted / permanentlyDenied
- 仅影响使用 `ensureLocationPermission` 的页面（目前为位置选择页）

**目录约定**：测试按领域划分，位置选择页属于 content/entry，路径 `test/ui/content/entry/widgets/`。

**适用场景与约束**：适用于需在 flutter_test 中隔离平台权限的场景。不适用：无权限依赖的页面。

## 未来演进

抽取 PermissionDeniedCard 共享组件。
