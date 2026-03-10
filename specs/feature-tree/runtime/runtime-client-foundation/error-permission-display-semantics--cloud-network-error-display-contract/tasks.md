# L4 任务：cloud-network-error-display-contract

## 当前交付任务

- [x] T0 specs/ux 规范已定义，07-error-permission-semantics.mdc 已创建
- [x] T0 测试目录迁移：create/publish → content/entry，integration/location → content/location（按领域服务划分）
- [x] T0 附近位置页、创作页已按规范实现（内联占位 / SnackBar）
- [ ] T1 抽取/暴露 CloudCodeToL10nMapper（或保持 _mapCloudCodeToMessage 内联，由 L1b 覆盖）
- [ ] T2 L1a 契约测试（可选）：CloudException.code→l10n key 映射表，`test/cloud/content/location/contract/`；删除纯 key 存在性断言
- [x] T3 L1b Widget 测试：位置选择页云端错误态，`test/ui/content/entry/widgets/location_selector_page_widget_test.dart`（FakeLocationService 抛 CloudException，FakeChecker 返回 granted；**依赖 permission-card T1**）
- [x] T4 L1b Widget 测试：位置选择页加载态（FakeChecker granted + nearby 延迟）
- [x] T5 L1c Journey 测试：`test/ui/content/entry/journeys/entry_location_error_journey_test.dart`，创作→选位置→云端超时→内联错误
- [x] T6 发现流加载失败迁移至内联占位（若当前为 SnackBar）
- [x] T7 创作页 loadFailed 等统一使用 context.l10n

## 搁置任务

无。

## 未来演进任务

- 抽取 CloudErrorInlinePlaceholder 共享组件
- 抽取 LocationPermissionChecker 接口（由 permission-card 承担）
