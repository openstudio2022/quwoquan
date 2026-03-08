# L2 端侧平台化重构 — 设计方案

## 设计动因

解决 spec.md 中 R4 全部约束：目录位置错误、数据层缺失、代码质量问题。这是所有其他 L2 的前置工作——必须先有干净的架构基础才能叠加新功能。

## 上游输入评审

- spec.md R4.1~R4.5 清晰，acceptance A1/A2/A7 可测。
- 依赖：
  - `app_router.dart`、`main_app_shell.dart`、`bottom_navigation.dart`（路由更新）
  - `app_providers.dart`（Provider 注册）
  - `AppContentRepository`（接口移除）
  - `PrototypeMockData`（数据迁移）
- 无阻断项。

## 对标输入分析

| 对标 | 借鉴点 | 适用边界 |
|------|--------|----------|
| chat 域迁移（Phase 2 已完成）| features/ → ui/chat/ 迁移模式 | 同项目已验证的迁移路径 |
| content 域（已有 cloud/services/content/）| Repository 三层模式 | 同项目已有标杆 |
| discovery 域（ui/discovery/）| providers/ + widgets/ 拆分 | 组件化参考 |

## 方案对比

### 迁移策略

#### 方案 A（选定）：一次性迁移 + 组件拆分

一步完成：目录迁移 → import 更新 → 组件拆分 → Repository 创建 → 硬编码清理。

**优点**：一次变更，避免中间态混乱
**缺点**：单次 PR 较大
**适用条件**：圈子代码体量可控（3 个页面文件）

#### 方案 B：分步迁移

先移目录不改代码 → 再拆组件 → 再清硬编码。

**优点**：每步 PR 小，易审查
**缺点**：多个中间态，互相依赖
**适用条件**：代码体量大、团队多人并行时

**选型决策**：**方案 A**。圈子当前仅 3 个页面文件（circles_page 1445 行、circle_detail_page 898 行、circle_stats_page），一次性迁移是最高效的。

### Repository 设计

#### 方案 A（选定）：按 service.yaml 完整映射

Abstract 接口方法与 service.yaml 11 个 API 一一对应，加上新增的 5 个存储 API 和 2 个 feed 管理 API，共 18 个方法。

```dart
abstract class CircleRepository {
  // --- 圈子基础 ---
  Future<PaginatedList<CircleDto>> listCircles({String? category, String? cursor, int limit = 20});
  Future<CircleDto> getCircle(String circleId);
  Future<CircleDto> createCircle(CreateCircleRequest request);
  Future<CircleDto> updateCircle(String circleId, UpdateCircleRequest request);
  Future<void> archiveCircle(String circleId);

  // --- 成员管理 ---
  Future<void> joinCircle(String circleId);
  Future<void> leaveCircle(String circleId);
  Future<PaginatedList<CircleMemberDto>> listMembers(String circleId, {String? cursor, int limit = 20});
  Future<void> updateMemberRole(String circleId, String userId, String role);

  // --- 内容 feed ---
  Future<PaginatedList<PostDto>> getCircleFeed(String circleId, {String? cursor, int limit = 20, String sort = 'latest'});
  Future<void> pinPost(String circleId, String postId, {required bool pinned});
  Future<void> featurePost(String circleId, String postId, {required bool featured});

  // --- 统计 ---
  Future<CircleStatsDto> getCircleStats(String circleId);

  // --- 存储空间 ---
  Future<PaginatedList<CircleFileDto>> listFiles(String circleId, {String? parentId, String? sort, String? cursor, int limit = 20});
  Future<CircleFileUploadResult> createFile(String circleId, CreateFileRequest request);
  Future<CircleFileDto> getFile(String circleId, String fileId);
  Future<CircleFileDto> updateFile(String circleId, String fileId, UpdateFileRequest request);
  Future<void> deleteFile(String circleId, String fileId);

  // --- 行为上报 ---
  Future<void> reportBehavior(CircleBehaviorReport report);
}
```

**方案 B（备选）**：分多个 Repository（CircleRepository + CircleStorageRepository + CircleFeedRepository）。不选，因 service.yaml 是单一 circle-service，端侧保持 1:1 映射最简。

**选型决策**：**方案 A**，单一 CircleRepository 对应单一 circle-service。

### 组件拆分策略

从 circles_page.dart（1445 行）提取：

| 组件 | 目标文件 | 提取来源 |
|------|----------|----------|
| `CircleCard` | `widgets/circle_card.dart` | 推荐区圈子卡片（封面 + 名称） |
| `ChannelPanel` | `widgets/channel_panel.dart` | 频道管理面板（拖拽排序 + 增删） |
| `DiscoveryPostCard` | `widgets/discovery_post_card.dart` | 瀑布流内容卡片（_DiscoveryPostCard） |
| `SubCategoryBar` | `widgets/sub_category_bar.dart` | 二级分类条（_SubCategoryBarDelegate + 内容） |
| `CircleActivityCard` | `widgets/circle_activity_card.dart` | 活动卡片区 |

从 circle_detail_page.dart（898 行）提取：

| 组件 | 目标文件 | 提取来源 |
|------|----------|----------|
| `CircleHeader` | `widgets/circle_header.dart` | 封面 + 头像 + 描述 + 统计 + 操作按钮 |
| `CircleStatChip` | `widgets/circle_stat_chip.dart` | _StatChip |
| `CircleActionButton` | `widgets/circle_action_button.dart` | _ActionButton |
| `CircleMoreMenu` | `widgets/circle_more_menu.dart` | _buildMoreMenu |

## 选型决策

| 决策项 | 选定方案 | 理由 |
|--------|----------|------|
| 迁移策略 | 一次性迁移 | 代码体量可控，避免中间态 |
| Repository | 单一 CircleRepository 18 方法 | 1:1 对应 circle-service |
| 组件拆分 | 9 个独立 Widget | 职责单一、可复用 |

## 关键设计决策

- **DK-1**：Mock 实现从 `PrototypeMockData` 搬到 `lib/cloud/services/circle/mock/circle_mock_data.dart`，结构保持不变但返回类型改为 DTO 类（非 `Map<String, dynamic>`）。
- **DK-2**：Remote 实现所有 URL 路径必须与 service.yaml routes 一致，使用 `CloudRuntimeConfig.gatewayBaseUrl`。
- **DK-3**：迁移时不做功能变更——视觉和行为完全不变，仅结构调整+代码质量提升。
- **DK-4**：硬编码清理优先级：字号 > 间距 > 圆角 > 颜色 > 尺寸 > 文案。circle_detail_page 有 40+ 处需修复。
- **DK-5**：circles_page 频道管理与 `circles-channel-management-panel` 特性对齐，该特性 acceptance.yaml 中的路径更新为 `lib/ui/circle/pages/circles_page.dart`。

## Story 与测试层映射

| L4 Story | T1 单元 | T2 集成 | T3 契约 | T4 E2E |
|----------|---------|---------|---------|--------|
| features-to-ui-migration-contract | import 检查（零 features/circles/ 引用）| app_router 导航 | — | 三页面可正常打开 |
| circle-repository-contract | Mock 返回正确类型 | Provider mock↔remote 切换 | 方法签名与 service.yaml 一致 | — |
| circle-semantic-cleanup-contract | verify_dart_semantic.py 通过 | — | — | — |

## 未来演进

- Repository 返回类型从 Map 升级为 codegen 生成的 DTO 类（在 codegen-app 就绪后执行）。
- 状态管理从 ConsumerStatefulWidget 迁移到 Notifier（圈子功能复杂度增加后执行）。

## 遗留带规划任务

- circle_stats_page.dart 的硬编码清理（体量较小，可在本次一并处理）。
- 更新 `circles-channel-management-panel` 特性的 acceptance.yaml 路径。
