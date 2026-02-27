# L3 特性：feed-item-dto-contract（Feed 规范 DTO 契约）

## 功能说明

从 `_projections/discovery_feed.yaml` metadata 驱动生成端侧 `FeedItemDto`（强类型 Dart 类），将 `ContentRepository` 输出统一为规范字段 DTO，消除 `discovery_page.dart` 中大量字段别名兜底链（`post['likes'] ?? post['likesCount'] ?? 0`）。同时迁移 mock 数据到规范字段，重组 `cloud/runtime/generated/` 为按业务域目录结构，与 `cloud/services/` 层保持一致。

## 职责边界

- **负责**：`_projections/discovery_feed.yaml` 的 `client_projection` 字段扩展；codegen 生成 `FeedItemDto` 类；mock 数据迁移与规范化；`generated/` 目录按域重组；`ContentRepository` 输出强类型 DTO；删除 `discovery_page.dart` 字段别名映射函数
- **不负责**：写操作（like/save/follow）——由 `content-action-intent-contract` 负责；视频/文章/微趣的 DTO 应用——各自 display-journey L3 负责

## 适用范围与约束

- **适用**：`content-display-journey-consistency` 内所有 display journey，所有消费 `FeedItemDto` 的 UI 组件
- **前置条件**：`_projections/discovery_feed.yaml` 已定义 `client_projection.fields`；`codegen_app_metadata` 工具可读取投影定义
- **不适用**：写操作（赞/收藏/关注）；圈子流等其他 feed 来源
- **约束**：
  - `generated/content/feed_item_dto.g.dart` 标记 `// Code generated ... DO NOT EDIT.`，禁止手改
  - 字段变更必须走 metadata → `make verify` → `make codegen-app` 流程
  - mock 数据字段必须与 `FeedItemDto` schema 100% 一致，由 contract test 验证
  - 不兼容旧有 `Map<String, dynamic>` 传参接口（本次重构不考虑兼容）

## 与父/子节点关系

| 节点 | 关系 |
|------|------|
| `content-display-journey-consistency`（L2） | 父节点 |
| `photo-display-journey`（L3） | 依赖本 L3 完成后才能做 DTO 集成（D19/D20） |
| `video/article/moment-display-journey`（L3） | 后续依赖，各自扩展 DTO 消费 |
| `content-action-intent-contract`（L3） | 并列，写操作层；本 L3 提供 DTO 读操作基础 |

## 验收标准概要

- A1：`FeedItemDto` 从 `_projections/discovery_feed.yaml` 生成，字段与 metadata 一致
- A2：mock 数据在 `content_mock_data.dart`，字段 100% 符合 `FeedItemDto` schema
- A3：`MockContentRepository` 和 `RemoteContentRepository` 均输出 `FeedItemDto`
- A4：`discovery_page.dart` 无 `_toXxxItem` 别名映射函数
- A5：`DiscoveryFeedProvider` 使用 `List<FeedItemDto>`
- A6：`cloud/runtime/generated/` 按域组织（`content/` 子目录）
- A7：`feed_item_dto_contract_test.dart` 通过，`make gate` 通过
