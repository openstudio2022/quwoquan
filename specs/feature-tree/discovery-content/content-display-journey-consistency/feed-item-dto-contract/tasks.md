# 开发任务：feed-item-dto-contract

## 当前交付任务

### metadata（M）

- [x] M1：扩展 `quwoquan_service/contracts/metadata/_projections/discovery_feed.yaml`，增加 `client_projection.fields` 节（规范字段列表：`id`、`type`、`authorId`、`displayName`、`avatarUrl`、`coverUrl`、`thumbnailUrl`、`title`、`body`、`likeCount`、`commentCount`、`favoriteCount`、`imageUrls`、`createdAt`；每字段含 `aliases` 列表用于 fromMap alias resolver codegen）
- [x] M2：`make verify`（metadata 内部一致性通过）

---

### codegen（C）

- [x] C1：`make codegen-app` 生成两个文件（工具已增强，可直接执行）：
  - `lib/cloud/runtime/generated/content/feed_item_dto.g.dart`（`FeedItemDto` 类 + `fromMap` alias resolver）
  - `lib/cloud/runtime/generated/content/content_metadata.g.dart`（原 `post_runtime_metadata.g.dart` 内容，路径迁移）
- [x] C2：全局替换旧 import 路径：将所有 `import '.../generated/post_runtime_metadata.g.dart'` 改为 `import '.../generated/content/content_metadata.g.dart'`；删除旧文件 `post_runtime_metadata.g.dart`
- [x] C3：验证生成文件内容正确（字段数量、alias resolver、DO NOT EDIT 头）

---

### 业务逻辑（A）

- [x] A1：重组 `lib/cloud/runtime/generated/` 目录为 `content/` 子目录（`post_runtime_metadata.g.dart` 已删除）
- [x] A2：新建 `lib/cloud/services/content/mock/content_mock_data.dart`，迁移 `discoveryPhotoData`、`discoveryVideoData`、`discoveryArticleData`、`discoveryMomentData` 的内容，统一使用规范字段名（与 `FeedItemDto` schema 一致）
- [x] A3：`app_providers.dart` 的 `_CurrentContentDataService.getDataList` 改为：调用 Repository 返回 `List<FeedItemDto>` 后执行 `dto.toMap()` 转换，维持 DataService 接口向下兼容
- [x] A4：`MockContentRepository.listDiscoveryFeedPage` 改为：`ContentMockData.xxx.map(FeedItemDto.fromMap).toList()`（不再返回 `Map<String, dynamic>`）
- [x] A5：`RemoteContentRepository.listDiscoveryFeedPage` 解析响应后通过 `FeedItemDto.fromMap(item)` 输出（统一出口）
- [x] A6：`DiscoveryFeedProvider` 类型改为 `Map<String, AsyncValue<DiscoveryFeedState>>`，`DiscoveryFeedState.items` 改为 `List<FeedItemDto>`
- [x] A7：`discovery_page.dart` 删除 `_toMomentItem`、`_toPhotoItem`、`_toVideoItem`、`_toArticleItem` 四个别名映射函数；用单一 `_buildFeedDisplayItem(FeedItemDto)` 替代（仅用规范字段，无别名链）；`_toTimeAgo`/`_toDate` 入参改为 `DateTime`

---

### 测试（T）

- [x] T1：新增 `quwoquan_app/test/cloud/content/post/contract/post_feed_dto_contract_test.dart`：三维度覆盖全部通过
  - group「PostFeedDto — 常规契约」：四类内容 canonical 字段解析、id/authorId/displayName 非空验证
  - group「PostFeedDto — 兼容性契约」：alias 字段解析（postId/authorNickname/likesCount）、toMap round-trip、copyWith 偏更新
  - group「PostFeedDto — 异常/边界契约」：缺失字段降级为零值、全字段缺失不崩溃
- [x] T2：`make build` ✓ / `make verify-metadata` ✓ / `flutter analyze` 0 error 0 warning ✓

---

## 类型化 DTO 拆分（第二阶段）✅

> 当前 `FeedItemDto` 是混合型大 DTO，下一阶段拆分为类型专属 DTO，photo/video 各自独立。
> **执行前置条件**：第一阶段全部任务 ✅ 完成。

### metadata（M）

- [x] M3：新建 `_projections/photo_post.yaml`，`client_projection` 定义 `PhotoPostDto`；在 `fields` 中增加 `width`（int, nullable）、`height`（int, nullable）
- [x] M4：新建 `_projections/video_post.yaml`，`client_projection` 定义 `VideoPostDto`；含 `width`、`height`、`durationMs`
- [x] M5：新建 `_projections/article_post.yaml`，`client_projection` 定义 `ArticlePostDto`
- [x] M6：新建 `_projections/moment_post.yaml`，`client_projection` 定义 `MomentPostDto`（含可选 imageUrls / videoUrl / durationMs）
- [x] M7：`make verify`（metadata 一致性通过）

### codegen（C）

- [x] C4：手写 `lib/cloud/runtime/generated/content/post_base_dto.dart`，定义抽象基类 `PostBaseDto`（含 `const` 构造器）；另有 `content_dtos.dart` barrel 文件提供 `postBaseDtoFromMap` 分发函数
- [x] C5：手写 `lib/cloud/runtime/generated/content/photo_post_dto.g.dart`（`PhotoPostDto extends PostBaseDto`，含 `width?`、`height?`、`aspectRatio` 计算属性）
- [x] C6：手写 `lib/cloud/runtime/generated/content/video_post_dto.g.dart`（`VideoPostDto extends PostBaseDto`，含 `width?`、`height?`、`durationMs?`、`aspectRatio`）
- [x] C7：手写 `lib/cloud/runtime/generated/content/article_post_dto.g.dart`（`ArticlePostDto extends PostBaseDto`）
- [x] C8：手写 `lib/cloud/runtime/generated/content/moment_post_dto.g.dart`（`MomentPostDto extends PostBaseDto`，含 `hasImages`/`hasVideo` 帮助属性）
- [x] C9：`flutter analyze` 验证 0 error 0 warning（DO NOT EDIT 头正确）

### 业务逻辑（A）

- [x] A8：`ContentMockData` photo 条目补充 `width` / `height` 字段（10 条全部补齐）
- [x] A9：`ContentMockData` video 条目补充 `width` / `height` 字段（3 条全部补齐；竖屏 1080×1920，横屏 1920×1080）
- [x] A10：`ContentRepository` 统一返回 `CursorPage<PostBaseDto>`；`postBaseDtoFromMap` 按 `contentType` 分发到具体子类；保留 `listDiscoveryFeedPageCurrent` 兼容层（FeedItemDto over PostBaseDto.toMap）
- [x] A11：`DiscoveryFeedProvider.DiscoveryFeedState.items` 类型改为 `List<PostBaseDto>`；`_buildFeedDisplayItem` 按子类型 (`is PhotoPostDto`/`is VideoPostDto`/等) 分支构建展示 Map，直接使用 `width`/`height` 计算 aspectRatio

### 测试（T）

- [x] T3：新增 `test/cloud/content/post/contract/post_dto_contract_test.dart` 三维度覆盖：
  - group「PostDto — 常规契约」：PhotoPostDto/VideoPostDto 解析 width/height/durationMs；PostBaseDto 多态；mock 数据 width>0&&height>0
  - group「PostDto — 兼容性契约」：alias resolver（imageWidth/videoWidth）；toMap round-trip；copyWith 偏更新
  - group「PostDto — 异常/边界契约」：全字段缺失不崩溃；null 值安全
- [x] T4：`flutter analyze lib/` 0 error 0 warning ✓

---

## 搁置任务（带规划）

| 任务 | 搁置原因 | 计划重启条件 |
|------|----------|-------------|
| `user/author_dto.g.dart` 生成 | 依赖 `user_profile/fields.yaml` 完善与 `UserRepository` 对齐 | `content-action-intent-contract` 完成后，配合 UserRepository 一起生成 |
| `make gate-full` 增加 DTO 字段 vs. `post/fields.yaml` 自动比对 | 需改 `verify_metadata` 脚本支持端云字段比对 | 待 gate 脚本增强时启用 |

---

## 未来演进任务

- `PhotoPostDto` / `VideoPostDto` 扩展为端侧 ViewModel（含 `aspectRatio`、`formattedLikeCount` 等 UI 计算字段），DTO 保持 DO NOT EDIT，ViewModel 包装层手写
- `FeedItemDto` 废弃：所有引用迁移完毕后删除 `feed_item_dto.g.dart`
