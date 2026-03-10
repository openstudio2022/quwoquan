# L4 任务：permission-card-display-contract

## 当前交付任务

- [x] T0 定位权限：附近位置页已实现 ensureLocationPermission、永久拒绝展示去设置
- [x] T0 相册权限：create_media_picker_page 已使用 mediaPickerPermissionDenied
- [x] T1 抽取 LocationPermissionChecker 接口（默认实现调 Geolocator，CreateLocationService/页面注入）
- [x] T2 L1b Widget 测试：`test/ui/content/entry/widgets/location_selector_page_widget_test.dart`，位置选择页权限永久拒绝 → 展示 locationAppPermissionRequired + 去设置
- [x] T3 通用 openSettings l10n key 补齐（locationOpenSettings 已存在）
- [ ] T4 L4 Patrol：真机权限拒绝 + 去设置跳转（deferred，advisory，不阻塞 gate）
- [ ] 相机/麦克风权限场景按同模式实现（当功能接入时）

## 搁置任务

无。

## 未来演进任务

- 抽取 PermissionDeniedCard 共享组件
