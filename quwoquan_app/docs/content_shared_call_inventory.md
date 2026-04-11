# 内容共用调用面清单（归档）

对 `lib/ui/**`、`lib/core/**` 中与 `appContentRepositoryProvider`、`discovery*Data`、`lookupDiscovery*`、`discoveryFeedWireRowByPostId`、`articleById` 相关的用法分类，便于阶段 A/B 收口与阶段 C 长期对齐。

## 1. 发现区 UI：已迁出 `AppContentRepository` 发现 Map API

| 位置 | 模式 |
|------|------|
| `lib/ui/discovery/pages/discovery_page.dart` | `mockDiscoveryWireFallback` + `ContentMockData.discovery*`；分享/wire 用 `prototypeDiscoveryWireRowForMock` |
| `lib/ui/discovery/pages/home_page.dart` | `MediaViewerExtra.rawPostsById`：`prototypeDiscoveryWireRowForMock` |
| `lib/ui/discovery/widgets/moment_social_feed.dart` | 同上 fallback + wire |
| `lib/ui/discovery/widgets/works_immersive_viewer.dart` | `_rawPostById`：`prototypeDiscoveryWireRowForMock` |

## 2. 非内容域：保留 `appContentRepositoryProvider`

| 位置 | 用途 |
|------|------|
| `lib/ui/chat/pages/chat_page.dart` | 加密会话等聊天原型数据（`read(appContentRepositoryProvider)`），**不属于**发现区共用整改范围 |

## 3. 实现与数据源（非 UI 直接调用）

| 位置 | 说明 |
|------|------|
| `lib/cloud/services/content/content_repository.dart` | `_allRawPosts` 等聚合 `ContentMockData.discovery*`（canonical） |
| `lib/cloud/services/app_content/app_content_repository_mock.dart` | 发现区 getter 委托 `ContentMockData`；`discoveryFeedWireRowByPostId` → `lookupDiscoveryFeedWireRow` |
| `lib/core/services/app_content_repository.dart` | 抽象类上发现区 getter / `articleById` / `discoveryFeedWireRowByPostId` 已 `@Deprecated`；`lookupDiscoveryFeedWireRow` 仍供 mock 与过渡 API 使用 |
| `lib/cloud/services/content/discovery_wire_lookup.dart` | **Canonical wire 查找**：`ContentMockData` 聚合 + `prototypeDiscoveryWireRowForMock` / `mockDiscoveryWireFallback` |

## 4. 阶段 C（长期）：`PrototypeMockData` 与帖子形状

| 位置 | 现状 |
|------|------|
| `lib/core/mock/prototype_mock_data.dart` | 仍含 `discoveryMomentData` / `discoveryPhotoData` 等 TSX 1:1 切片；`articleById` 由 `MockAppContentRepository` 委托。目标：与 `ContentMockData` + metadata/codegen projection 对齐后削减重复 Map |

## 5. 检索命令（复跑）

```bash
rg "appContentRepositoryProvider|discoveryMomentData|discoveryPhotoData|discoveryArticleData|discoveryVideoData|lookupDiscoveryFeedWireRow|lookupDiscoveryPostBaseDto|discoveryFeedWireRowByPostId|articleById" quwoquan_app/lib/ui quwoquan_app/lib/core
```
