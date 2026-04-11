# 帖子（图/视频/文章）投影管线 — 页面与挂靠面清单

> **目的**：在「同一领域模型」下，显式区分 **Wire DTO**、**只读多表面投影（ReadPresentation + SurfaceSpec）**、**可编辑 Draft**、**存储/同步形态**，并完成逐面实施与验收。  
> **门禁（2026-04-11）**：帖子相关页已完成 ReadPresentation+Surface 与创作链 draftPreview 收口；矩阵 **P2=✓**、清单 **`compliant`**。下列表保留为 DoD 参照。

## 1. 完成定义（Definition of Done）

| 层级 | 要求 | 当前典型缺口 |
|------|------|----------------|
| **Wire / API DTO** | `PostBaseDto` 族与 metadata/codegen 一致；Repository 出口无业务 `Map` | 持续审计 Remote 边界 |
| **只读 ReadPresentation** | 每表面 **PostReadSurfaceId** + `PostReadProjectionFacade` / `PostSummaryView.readPresentation` | 已落地；新表面需补枚举与 facade switch |
| **SurfaceSpec** | 关注流 / 沉浸 / 圈子 / 个人主页 / 搜索 / 详情 / draftPreview 等数据化 | `PostReadSurfaceId`（codegen） |
| **Edit Draft** | **Draft → ReadPresentation（预览）** 与 **Draft → CreatePayload** 经 `publish_draft_projection_bridge` | 长文/发布确认已接 `postReadPreviewBundle*` |
| **存储投影（可选）** | 本地缓存/离线草稿字段与云契约可追踪 | 未统一文档化 |

**P2 记为 ✓ 的条件（帖子相关页）**：上述 **ReadPresentation（至少本页所用 Surface）+ 本页涉及编辑时的 Draft→Payload** 已接好，且清单 `status` 改回 `compliant`。

## 2. 页面与挂靠组件矩阵（实施顺序建议）

| 优先级 | 类型 | 路径 / 挂靠 | 用户场景 | 依赖 |
|--------|------|----------------|----------|------|
| P0 | 页面 | `lib/ui/discovery/pages/home_page.dart` | 关注/首页 Feed | Feed `PostBaseDto` → ReadPresentation(feed) |
| P0 | 页面 | `lib/ui/discovery/pages/discovery_page.dart` | 发现（微趣/视频等） | 同上 + 沉浸入口 |
| P0 | 组件 | `lib/components/content/media_post_card.dart` | 卡片复用 | 接收 ReadPresentation + SurfaceSpec |
| P0 | 页面 | `lib/ui/content/pages/unified_media_viewer_page.dart` | 侵入式浏览 | ReadPresentation(immersive) + wire 补全 |
| P0 | 组件 | `lib/ui/discovery/widgets/works_immersive_viewer.dart` | 沉浸滑卡（**非 `*_page`，矩阵不单独占行**） | 与 `unified_media_viewer` 共用投影 |
| P1 | 页面 | `lib/ui/circle/pages/home_circles_hub_page.dart` | 圈子 Tab 流 | 去掉/收敛 `CircleHubFeedPostEntry.raw`；DTO→Presentation |
| P1 | 页面 + 挂靠 | `lib/ui/circle/pages/circle_detail_page.dart` → `section_creations.dart` | 圈子内作品 | `_tryParsePost(Map)` → 管道入口 |
| P1 | 页面 | `lib/ui/user/pages/my_profile_page.dart` / `other_profile_page.dart` | 个人主页 | `profile_works_tab` / `profile_moments_tab` |
| P1 | 组件 | `lib/ui/user/widgets/profile_works_tab.dart` | 作品栅格 | `PostSummaryView.fromDto` → 表面化 |
| P1 | 组件 | `lib/ui/user/widgets/profile_moments_tab.dart` | 微趣列表 | 同上 |
| P2 | 页面 | `lib/ui/content/pages/article_detail_page.dart` | 文章详情 | `getPost` → ReadPresentation(detail_article) |
| P2 | 页面 | `lib/ui/content/pages/photo_detail_page.dart` | 图文详情 | ReadPresentation(detail_photo) |
| P2 | 页面 | `lib/ui/content/pages/video_detail_page.dart` | 视频详情 | ReadPresentation(detail_video) |
| P2 | 页面 | `lib/ui/search/pages/search_network_results_page.dart` | 搜索结果含帖子 | `SearchHit` → post 分支 ReadPresentation(search_card) |
| P2 | 页面 | `lib/ui/search/pages/global_search_page.dart` | 全局搜索（含内容命中） | 同上 |
| P3 | 创作链 | `create_page.dart`、`article_typography_page.dart`、`video_editor_page.dart`、`publish_*` | 编辑/预览/提交 | `postReadPreviewBundleFromCreateEditorState` / `postReadPreviewBundleFromPublishConfirmSummary`（draftPreview）+ `buildCreatePostPayloadMap` |
| — | 非页面 | `lib/ui/content/share/content_share_template.dart` | 分享 | `PostReadPresentation.fromPostBase` 生成 share 标题/摘要/封面 |

## 3. 与清单 / 矩阵的对应关系

- **占 `metadata_driven_ui_gap_inventory.yaml` 行**的：上表中所有 `*_page.dart` + `media_post_card.dart`（已在 content 域）。
- **仅占本文档、不占矩阵数据行**：`works_immersive_viewer.dart` 等；验收结论写在父页面 P2 备注或本文 §2。

## 4. 变更记录

| 日期 | 说明 |
|------|------|
| 2026-03-30 | 初版：帖子投影管线全量面清单；驱动 P2 与清单 `partial` 收口标准 |
| 2026-04-11 | 全量收口：门面+各表面 wire；`works_immersive_viewer`/`unified_media_viewer`/`section_creations`/profile/search/详情/创作链/分享模板已接；清单 compliant + 矩阵 P2 ✓ |
