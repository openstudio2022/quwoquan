# Design: unified-presentation-model

承接 [spec.md](spec.md)。本设计冻结统一只读 presentation model（`ContentSurfaceView`）的端侧落地方案、迁移灰度与测试矩阵。仅收敛读侧，不动写链路。

## 设计决策

### 决策 1：单一只读 model vs. 每 surface 适配器

| 方案 | 优点 | 缺点 | 选择 |
|------|------|------|------|
| A. 单一 `ContentSurfaceView`，四 surface 共享 | 唯一真相源、字段口径强一致、A4/口碑接入一处 | 需一次性定义全字段，初期改动面大 | ✅ 选定 |
| B. 保留四套，仅抽公共 mixin | 改动小 | 仍是四套口径，债务未清，违背 R24 | ✗ |
| C. 每 surface 独立 ViewModel + 共享 mapper | surface 定制灵活 | mapper 易再分叉，回到多真相源 | ✗ |

选定 A：定义单一 `ContentSurfaceView` + 单一 mapper `ContentSurfaceViewMapper.fromDto(PostBaseDto)`，四 surface 只读消费。

### 决策 2：媒体类型分支表达

- 不使用 `is/as PhotoPostDto` 等运行时类型判断（违反 04-dart-polymorphism）。
- `ContentSurfaceView` 持 `contentType`（来自 DTO 契约字段）+ 强类型可选字段（`mediaRefs` / `videoRef` / `articleSummary`）。
- mapper 内按 `contentType` 填充对应字段；surface widget 按 `contentType` 选择渲染分支，读取已填充的强类型字段。

### 决策 3：wire 投影去裸 Map

- 现状 immersive：`_wireMapForPresentation` 产 `Map<String,Object?>` → `ArticleDetailView`。
- 现状 `discoveryPresentationWireForPost(...)` 返回 `Map<String,dynamic>?`。
- 目标：新增强类型 `ContentSurfaceWire`（或直接复用 `ContentSurfaceView` 的子结构）承载渲染所需投影；`discoveryPresentationWireForPost` 改返回强类型（与 D2 接口拆分同批）。
- detail `PostSummaryView.fromDto({wire})`：保留类型签名过渡期可用，但内部改为从 `ContentSurfaceView` 适配；标 `@Deprecated` 引导迁移。

### 决策 4：迁移灰度

- 引入运行时 flag `unified_surface_view`（沿用现有 runtime config flag 机制）。
- 双读：flag on → mapper 产 `ContentSurfaceView`；flag off → 旧投影路径。
- 逐 surface 切换顺序：feed → detail → share → immersive（immersive 与 article-reader 耦合最深，最后切，受 pageflip 规则约束）。
- 旧路径在四 surface 全切并稳定一个迭代后，旧投影类移除（本轮只标 `@Deprecated`）。

## `ContentSurfaceView` 模型设计

```
class ContentSurfaceView {
  final String postId;
  final ContentType contentType;        // micro/image/video/article（+ 未来 review）
  final AuthorRef author;               // id / displayName / avatarUrl
  final String? title;                  // article 必有；其余可空
  final String? body;                   // micro/article 摘要
  final MediaRef? cover;                // article 封面 / video 首帧
  final List<MediaRef> images;          // image 多图
  final VideoRef? video;                // video 单视频 + durationMs
  final ContentStats stats;             // like/comment/share/view
  final DateTime createdAt;
  final List<IntersectionReason> intersectionReasons; // 承接 A4
  final SurfaceReferralContext referral;// position / feedRequestId（不展示，仅透传埋点）
}
```

- `MediaRef` / `VideoRef` / `AuthorRef` / `ContentStats` 为强类型小对象（替代裸 Map 字段）。
- 字段集与 fallback 对齐 `contracts/metadata/content/post/fields.yaml` 与 discovery 投影。

## 端侧落地结构

- 新增 `quwoquan_app/lib/ui/content/models/content_surface_view.dart`（model + 强类型子对象）。
- 新增 `quwoquan_app/lib/ui/content/models/content_surface_view_mapper.dart`（`fromDto` 单一映射，含 fallback）。
- feed：`moment_social_feed.dart` 卡片改读 `ContentSurfaceView`（拆分见 D3）。
- immersive：`works_immersive_viewer.dart` 去 `_rawArticleDataFor`/`_wireMapForPresentation`，改 `ContentSurfaceView`。
- detail：`post_summary_view.dart` / `post_read_projection_facade.dart` 适配统一 model，旧类 `@Deprecated`。
- share：`content_share_template.dart` 复用统一 model 字段。

## 与 D2/D3 协同

- D2（接口拆分 + `discoveryPresentationWireForPost` 去裸 Map）：本设计的强类型 wire 即 D2 的去裸 Map 目标类型，同批落地。
- D3（超大文件强拆）：四 surface 接入统一 model 时顺带把 `works_immersive_viewer`/`discovery_page`/`moment_social_feed` 拆到 <500 行。

## 观测与回滚

- 观测：mapper 产出失败计数、新旧路径字段 diff 抽样、surface 渲染异常上报（结构化 RuntimeFailure）。
- 回滚：`unified_surface_view` flag 关闭即回退；旧投影类未删除，回滚无损。

## 测试矩阵

| 验收 | T1 | T2 | T3 | T4 |
|------|----|----|----|----|
| A1 model 定义/字段对齐 metadata | required | optional | — | — |
| A2 mapper 四类型投影一致 | required | required | — | — |
| A3 四 surface 同源消费 | optional | required | — | — |
| A4 去裸 Map / 强类型 wire | required | optional | — | — |
| A5 灰度/回滚/Deprecated | required | required | — | optional |

- T1：`content_surface_view` 投影契约测试（四类型字段集对齐 metadata fixture）。
- T2：四 surface 同源 widget 测试（同一 DTO 经 mapper → feed/immersive/detail/share 同字段断言）。
