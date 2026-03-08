# L2 端侧平台化重构 — 任务列表

## 当前交付任务

### L3: directory-migration

- [ ] T1: [目录] 创建 `lib/ui/circle/` 及子目录 `pages/`, `providers/`, `widgets/`, `models/`
- [ ] T2: [迁移] 将 `lib/features/circles/pages/circles_page.dart` → `lib/ui/circle/pages/circles_page.dart`
- [ ] T3: [迁移] 将 `lib/features/circles/pages/circle_detail_page.dart` → `lib/ui/circle/pages/circle_detail_page.dart`
- [ ] T4: [迁移] 将 `lib/features/circles/pages/circle_stats_page.dart` → `lib/ui/circle/pages/circle_stats_page.dart`
- [ ] T5: [路由] 更新 `app_router.dart` 中 CirclesPage、CircleDetailPage、CircleStatsPage 的 import 路径
- [ ] T6: [路由] 更新 `main_app_shell.dart` 中 CirclesPage 的 import 路径
- [ ] T7: [清理] 删除 `lib/features/circles/` 目录
- [ ] T8: [验证] 全项目搜索确认零 `features/circles/` 引用，flutter analyze 通过

### L3: circle-repository-creation

- [ ] T9: [Repository] 创建 `lib/cloud/services/circle/circle_repository.dart`：Abstract 接口 18 方法
- [ ] T10: [Mock] 创建 `lib/cloud/services/circle/mock/circle_mock_data.dart`：从 PrototypeMockData 搬迁圈子 mock 数据
- [ ] T11: [Mock] 在 circle_repository.dart 实现 MockCircleRepository（调用 circle_mock_data）
- [ ] T12: [Remote] 在 circle_repository.dart 实现 RemoteCircleRepository（CloudRuntimeConfig + CloudRequestHeaders，URL 与 service.yaml 一致）
- [ ] T13: [Provider] 在 `app_providers.dart` 注册 `circleRepositoryProvider`（appDataSourceModeProvider 切换）
- [ ] T14: [清理] 从 AppContentRepository abstract 接口和 Mock/Remote 实现中移除 circlesCategoryConfig, circlesMockCircles, circlesMockActivities, circlePageCircleInfo
- [ ] T15: [清理] 从 PrototypeMockData 中移除圈子相关 mock 数据（circlesCategoryConfig, circlesMockCircles, circlesMockActivities, circlePageCircleInfo）
- [ ] T16: [迁移] 更新 circles_page.dart 和 circle_detail_page.dart 中的数据访问：从 `ref.read(appContentRepositoryProvider).circlesMockCircles` 改为 `ref.read(circleRepositoryProvider).listCircles()`
- [ ] T17: [测试] 契约测试：CircleRepository abstract 接口方法签名与 service.yaml API 一致

### L3: circle-code-quality

- [ ] T18: [组件拆分] 从 circles_page.dart 提取 5 个独立 widget（CircleCard, ChannelPanel, DiscoveryPostCard, SubCategoryBar, CircleActivityCard）到 `lib/ui/circle/widgets/`
- [ ] T19: [组件拆分] 从 circle_detail_page.dart 提取 4 个独立 widget（CircleHeader, CircleStatChip, CircleActionButton, CircleMoreMenu）到 `lib/ui/circle/widgets/`
- [ ] T20: [硬编码清理] circle_detail_page.dart 所有硬编码字面量替换为语义标签
  - 字号：22/18/15/14/13/12/11/10 → AppTypography.*
  - 间距：8/12/16/24/96 → AppSpacing.*
  - 圆角：12/16/20/24/32/40/48/56 → AppSpacing.*BorderRadius
  - 尺寸：128/56/48/4/10 → AppSpacing.*
  - 文案：'分享圈子'/'保存封面'/'举报圈子' → UITextConstants.*
- [ ] T21: [硬编码清理] circle_stats_page.dart 硬编码字面量替换
- [ ] T22: [硬编码清理] circles_page.dart 检查并修复残留硬编码（当前整体规范，逐一确认）
- [ ] T23: [import] 所有圈子文件 import 改为绝对路径 `package:quwoquan_app/ui/circle/...`
- [ ] T24: [验证] 运行 `python3 scripts/verify_dart_semantic.py` 对 ui/circle/ 零新增违规
- [ ] T25: [验证] 运行 `flutter analyze` 无新增错误

### 跨切任务

- [ ] T26: [特性树] 更新 `circles-channel-management-panel` acceptance.yaml 路径为 `lib/ui/circle/pages/circles_page.dart`
- [ ] T27: [特性树] 更新 `tree_index.yaml` 中 circle-community 下新增 L2 节点条目

## 搁置任务

- [ ] 状态管理迁移到 Notifier（重启条件：圈子功能复杂度增加需要更好的状态隔离）
- [ ] Repository 返回类型升级为 codegen DTO（重启条件：make codegen-app 就绪）

## 未来演进任务

- [ ] circles_page 频道配置从 mock Map 迁移到 DomainTaxonomy 驱动（L2 circle-experience-redesign 完成后）
- [ ] circle_detail_page 从当前结构升级为板块式（L2 circle-experience-redesign 完成后）
