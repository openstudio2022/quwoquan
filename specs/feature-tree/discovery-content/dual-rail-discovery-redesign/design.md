# dual-rail-discovery-redesign 设计

## 设计动因

当前发现页采用 `[美图][视频][微趣][文章]` 四 Tab 并列格式分类，存在三个核心问题：

1. **视觉疲劳**：精品大片（摄影/视频）与日常吐槽（微趣）混杂在同等视觉权重的 Tab 下，互相稀释
2. **认知负担**：用户必须主动选择"格式"而非沉浸在"内容气质"中
3. **精品感缺失**：美图/视频/文章三类精品内容分离，无法形成沉浸式连续审美体验

**解决方向**：动静分离 + 气质分轨。微趣承担高频社交"烟火气"，作品承担深度审美"沉浸感"。

## 适用场景与约束

**适用**：
- quwoquan App 的发现页 UX 重构（Dart/Flutter 端侧）
- 用户基数尚小、内容量有限时，服务端混排可先用规则策略（最新/随机），成本低

**约束与局限性**：
- 依赖服务端提供统一 `works-feed` 端点（混排职责上移）；端侧无法自主控制混排顺序
- 文章卡片分页采用服务端预切（`pages: List<String>`），需后端配合；无法支持完全自由排版
- 真正的 CSS float 文字环绕不可行（Flutter 渲染限制），降级为行内块排版（视觉上已足够杂志感）
- 点位评论 P2（坐标持久化）依赖评论服务 API 扩展，本期仅实现 UI 光点入口

## 关键决策

### 1. 双轨架构取代四 Tab

**备选方案对比**：

| 方案 | 描述 | 优点 | 缺点 |
|------|------|------|------|
| **A（选定）双轨道** | `[微趣][作品]`，作品内部垂直混排 | 气质分离清晰，沉浸感强，减少决策负担 | 需新 API 端点；三类媒体手势需精细协调 |
| B 保持四 Tab | 仅优化各 Tab 内交互 | 改动小，风险低 | 未解决根本问题，精品感仍差 |
| C 全混排单流 | 所有内容统一一条 feed | 最简单 | 微趣与作品气质冲突，仍然混乱 |

选择方案 A，核心原因：动静分离是解决"视觉疲劳"的唯一有效路径。

### 2. 作品 feed = 服务端混排

- 端点：`GET /v1/content/works-feed?filter_type=&cursor=&limit=`
- `filter_type` 为空 = 全部混排；`image`/`video`/`article` = 类型筛选
- 服务端初期策略：按时间+类型交替（规则排序），后续接推荐信号
- 响应类型：`CursorPage<PostBaseDto>`，通过 `postBaseDtoFromMap()` 多态派发

### 3. 文章内容格式升级

- **当前**：`body: String`（纯文本）
- **目标**：`blocks: List<ArticleBlock>`（结构化块）
- `ArticleBlock` 多态：`TextBlock`、`ImageBlock`（width_fraction/float_side/caption）、`QuoteBlock`
- **图片行内布局（方案 A，行内块）**：`half`/`third` 宽度图片用 `Row(Image + Expanded(Text))`，`full` 宽度图片用 `Column(Image + Caption)`；不实现 CSS float（Flutter 渲染不支持，成本高）
- 图片宽高比约束：最大 9:16

### 4. 场景切换主题方案

- 沿用已有 `videoForceDarkProvider` 模式，扩展为 `worksForceDarkProvider`
- 进入作品频道时：`AnimatedContainer` / `TweenAnimationBuilder` 400ms 背景色渐变至 `#0A0E14`
- 作品频道下所有子页面用 `Theme(data: worksThemeData, child: ...)` 包裹
- 文章专属色彩：`AppArticleColors` 常量集（不依赖 ThemeData.textTheme，因需要特定银灰色调）

### 5. 色彩体系

| 角色 | 颜色 | 值 |
|------|------|----|
| 品牌主色（浅背景） | 克莱因蓝 | `#002FA7` |
| 品牌主色（深色背景变体） | 作品蓝 | `#4A8BF5` |
| 作品背景 | 墨浆蓝 | `#0A0E14` |
| 文章正文 | 银灰 | `#B8C0CC` |
| 文章标题 | 近白 | `#E8EDF3` |
| 文章引用竖线 | 克莱因蓝 | `#002FA7` |
| 图注小字 | 暗灰 | `#6B7585` |
| 美图进度条 | 作品蓝 | `#4A8BF5` |
| 点位光点 | 克莱因蓝（脉冲） | `#002FA7` |

### 6. 手势优先级设计

```
Priority 1: 水平翻页（图集/文章卡片/视频系列）—— 阈值低，优先竞争
Priority 2: 长按 500ms → 点位光点 + 锁定 PageView
Priority 3: 右侧 40% 热区 → Drawer 展开
Priority 4: 垂直分页切换作品（阈值高，角度 > 45° 偏向垂直触发）
系统返回: 边缘 15px 保护区，HorizontalDragGestureRecognizer 排除
```

### 7. 字体方案

- 作品文章正文：思源宋体（`Source Han Serif` / `NotoSerifSC`），Google Fonts 或本地 assets
- 微趣正文：系统默认字体（无衬线），不引入额外字体
- 字体注册：`pubspec.yaml` → `fonts:` 节点，assets 目录 `assets/fonts/source_han_serif/`

## 现有代码与目标态对照

| 现有 | 目标 | 处理方式 |
|------|------|----------|
| `discovery_page.dart`（1813行，四 Tab） | 双轨架构，拆分为多文件 | 重构，不保留旧 Tab 结构 |
| `discoveryFeedMapProvider`（四 category）| 新增 `worksFeedProvider` + 保留 `momentFeedProvider` | 新建，旧 provider 逐步淡出 |
| `ArticlePostDto.body: String` | `ArticlePostDto.blocks: List<ArticleBlock>` | metadata 变更 → codegen |
| `videoForceDarkProvider` | 扩展为 `worksForceDarkProvider` | 扩展，不破坏兼容 |
| 内容 Tab：`photo/video/moment/article` | 作品 Tab `filter_type`；微趣独立 | 新 Tab 枚举，旧枚举废弃 |

## 数据流（目标态）

```
service.yaml (works-feed endpoint)
    │ make codegen
    ▼
ContentRepository.listWorksFeedPage(filterType, cursor)
    │
    ▼
WorksFeedProvider (AsyncNotifier<CursorPage<PostBaseDto>>)
    │
    ├── WorksImmersiveViewer
    │       ├── PhotoGalleryItem (PhotoPostDto)
    │       ├── VideoAutoPlayItem (VideoPostDto)
    │       └── ArticleCardItem   (ArticlePostDto + blocks)
    │
MomentFeedProvider (独立，moment category 不变)
    │
    └── MomentSocialFeed
            ├── MomentImageGrid
            ├── MomentTextCard (5行截断)
            └── MomentVideoCard (入焦自动播放)
```

## 未来演进

| 演进项 | 前置条件 | 对应 tasks |
|--------|----------|------------|
| 点位评论坐标持久化（P2） | 评论服务 API 扩展，`Comment` 模型增加 `position_x/y` | `works-annotation-dot` tasks 中的搁置任务 |
| 服务端推荐混排（取代规则排序） | `feed-orchestration-recommendation/personalized-ranking` 完成 | — |
| 文章卡片分页优化（客户端文字分页） | 评估 Flutter `RenderParagraph` metrics 可行性 | `article-magazine-cover` 搁置任务 |
| 微趣双列瀑布流切换按钮 UI 精细化 | 基础版交付后用户反馈驱动 | `moment-social-feed` 演进任务 |

## 当前实现同步（2026-02-26）

- 已落地双轨主导航与作品沉浸容器：`DiscoveryPage` 主 Tab 居中，`WorksImmersiveViewer` 接管作品轨沉浸视图。
- 已落地微博式作品一级交互：`作品` 文案右侧箭头展开/收起二级筛选；仅首次进入作品自动展开 1.5s。
- 已落地固定工具栏形态：顶部指标与底部作者/动作条均固定悬浮，内容区保持清洁，不随垂直切页滚动。
- 已落地作品内部指标：由总作品指标调整为当前作品内部 `current/total`（图组、文章卡片、视频合集）。
- 已落地文章阅读升级：mock 多卡片数据 + 封面页 + 横向卡片阅读页；支持 `full/half/third` 图文布局与图注。
- 未完成项：works-feed 服务端混排契约、ArticleBlock metadata/codegen 化、真实视频自动播放与音量淡入。
