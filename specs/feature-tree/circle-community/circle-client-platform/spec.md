# L2 规格：端侧平台化重构

## 背景与动机

圈子端侧代码当前存在三个结构性问题：

1. **目录位置错误**：代码仍在 `lib/features/circles/`，按架构约束应在 `lib/ui/circle/`。
2. **数据层缺失**：无独立 CircleRepository，圈子数据混在 AppContentRepository 的 mock 中，无法接入云端 API。
3. **代码质量**：circle_detail_page.dart 存在 40+ 处硬编码视觉字面量（字号/间距/尺寸/圆角），违反编码规范。

本 L2 目标：完成圈子端侧的平台化重构，为后续功能迭代（存储空间、群聊、领域对齐）奠定干净的代码基础。

## 目标用户

- 开发团队：需要干净的代码架构来高效迭代圈子功能。

## 功能范围

### L3: directory-migration（目录迁移）

- `lib/features/circles/pages/` → `lib/ui/circle/pages/`。
- 创建 `lib/ui/circle/providers/`、`lib/ui/circle/widgets/`、`lib/ui/circle/models/` 子目录。
- 更新 `app_router.dart`、`main_app_shell.dart`、`bottom_navigation.dart` 中的 import 路径。
- 从大 Widget 文件中提取独立组件：CircleCard、ChannelPanel、DiscoveryPostCard、StatChip、ActionButton、MoreMenuItem。
- 更新 acceptance.yaml 中引用 `features/circles/` 的路径（如 circles-channel-management-panel）。

### L3: circle-repository-creation（Repository 创建）

- 创建 `lib/cloud/services/circle/circle_repository.dart`：Abstract 接口 + Mock 实现 + Remote 实现。
- Abstract 接口方法与 service.yaml API 一一对应（listCircles, getCircle, createCircle, joinCircle, leaveCircle, getCircleFeed, getCircleStats, listMembers）。
- Mock 实现：从 PrototypeMockData 提取圈子数据到 `lib/cloud/services/circle/mock/circle_mock_data.dart`。
- Remote 实现：使用 CloudRuntimeConfig.gatewayBaseUrl + CloudRequestHeaders。
- 在 `app_providers.dart` 注册 `circleRepositoryProvider`。
- 从 AppContentRepository 中移除 circles* 相关接口和实现。

### L3: circle-code-quality（代码质量清理）

- circle_detail_page.dart 所有硬编码字面量替换为语义标签。
- 所有圈子页面 import 改为绝对路径 `package:quwoquan_app/ui/circle/...`。
- 操作文案硬编码（'分享圈子'、'保存封面'、'举报圈子'）替换为 UITextConstants。
- 运行 `python3 scripts/verify_dart_semantic.py` 对 ui/circle/ 零新增违规。

## 不做什么（Out of Scope）

- 不做功能变更——纯结构迁移 + 代码质量，用户感知不变。
- 不做 Remote 实现的实际联调——先保证 Mock 切换正常。
- 不做状态管理重构（保持现有 ConsumerStatefulWidget 模式，后续按需迁移到 Notifier）。

## 约束

- 迁移过程中不得出现功能退化。
- 所有路由路径（/circles、/circle/:id、/circle/:id/stats）保持不变。
- PrototypeMockData 中的圈子 mock 数据迁移到 circle_mock_data.dart 后，原处删除。

## 验收重点

- A1（L1）：目录迁移完成，无存量 features/circles/ 引用。
- A2（L1）：CircleRepository 三层模式创建完成并注册。
- A7（L1）：硬编码清零，语义化审计通过。