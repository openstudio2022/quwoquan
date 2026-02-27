# L2 特性：dual-rail-discovery-redesign

## 功能说明

对发现页进行范式级重构，从"格式分类 Tab 导航"切换为**气质双轨架构**：

- **微趣（Moment）轨**：明亮社交场，高频互动，微博风格大图信息流
- **作品（Works）轨**：沉浸数字画廊，精品内容，三类媒体（视频/美图/文章）统一垂直分页流

**取代声明**：本特性在 UX 架构层面取代 `content-display-journey-consistency` 的呈现层（四 Tab 并列格式分类）。DTO 契约（FeedItemDto）与意图层（ContentIntentNotifier）继续沿用，不重复建设。

## 范围

- **双轨架构**：顶部 `[微趣][作品]` 主 Tab，400ms 关灯/开灯场景切换动画
- **微趣轨**：单列/双列瀑布流切换，自适应图片宫格，文字 5 行截断就地展开，视频入焦自动播放
- **作品轨**：服务端混排统一 works-feed，垂直强制分页，Tab 1.5s 呼吸收起，筛选参数化
- **三类媒体专属交互**：美图水平翻页 + 进度条，视频自动播放音量淡入，文章封面模式 + 卡片分页
- **毛玻璃 Drawer**：右侧 40% 热区，`BackdropFilter` sigma ≥ 15，深蓝沉浸色调
- **点位评论**（P1 UI）：长按 500ms 克莱因蓝脉冲光点，点击打开 Drawer；P2 坐标持久化暂不实施
- **文章富文本**：`blocks: List<ArticleBlock>` 替代纯 `body: String`，支持 half/third/full 宽度图片行内块

## 适用范围与约束

- **适用**：发现页（`DiscoveryPage`）及直接子页面（MediaViewer、ArticleViewer）
- **前置条件**：
  - `feed-item-dto-contract` 已完成（FeedItemDto codegen 基础）
  - `content-action-intent-contract` 已完成（赞/收藏/关注意图层）
- **不适用**：圈子流、个人主页、搜索结果；后端推荐算法排序逻辑（由 `feed-orchestration-recommendation` 负责）
- **约束**：
  - 新增 API 端点必须走 `service.yaml` → `make verify` → `make codegen` 流程
  - ArticleBlock DTO 变更走 metadata → codegen，禁止手改 `.g.dart` 文件
  - 色彩常量必须在 `AppColors` / `AppArticleColors` 中定义，禁止硬编码十六进制
  - 字体（思源宋体）必须通过 `pubspec.yaml` 声明，通过 `assets/fonts/` 注册
  - 手势优先级：水平翻页 > 长按点位 > Drawer 热区 > 垂直分页；边缘 15px 保护系统返回

## 与父/子节点关系

| 子节点 | 职责 | 执行顺序 |
|--------|------|----------|
| **works-unified-feed** | 服务端混排 works-feed API 契约 + codegen | 1（前置） |
| **article-rich-content-blocks** | ArticleBlock 富文本 DTO 契约 + codegen + 块渲染 | 1（前置，与 works-feed 并行） |
| **works-immersive-viewer** | 作品垂直沉浸 PageView + 通用交互 + 三类媒体专属 | 2（依赖前两项） |
| **moment-social-feed** | 微趣微博风格社交流（独立，与 works-immersive-viewer 并行） | 2 |

## 验收标准概要

- **A1** 双轨切换：400ms 关灯动画流畅，`worksForceDarkProvider` 正确切换主题
- **A2** 作品流加载：垂直强制分页，首屏 works-feed 加载，滑到底追加分页，无内容跳变
- **A3** Tab 呼吸：1.5s 后收起动画，Elastic 弹性展开，筛选切换触发重新请求
- **A4** 美图：水平翻页 + 环境色模糊背景 + 蓝色进度条
- **A5** 视频：自动播放 + 音量 500ms 淡入 + 水平滑系列/集合卡
- **A6** 文章：封面模式（高清图 + 衬线标题）+ 卡片横翻 + 块渲染图片行内布局
- **A7** 微趣：自适应宫格，5 行截断就地展开，视频入焦自动播放
- **A8** Drawer：右侧 40% 宽，`BackdropFilter` sigma ≥ 15，正确定位不遮挡系统 UI
- **A9** 点位光点：长按 500ms 触发，PageView 锁定，光点脉冲动画，点击打开 Drawer
- **A10** `make gate` 通过：DTO 契约一致，codegen hash 匹配，Mock/Remote 全链路正确

## 当前实现状态（2026-02-27）

- **已落地（端侧）**
  - 主导航居中化：`微趣/作品` 在发现页主头部居中，切换时位置保持稳定；Tab 字号与间距按 3 档位响应式自适应。
  - 作品一级交互：`作品` 右侧下拉箭头展开/收起二级筛选；首次进入作品自动展开 1.5s 后收起，后续由用户手动控制。
  - 作品沉浸容器：垂直分页浏览、右侧毛玻璃评论抽屉、长按蓝色光点评论入口、顶部/底部工具栏固定悬浮。
  - **作品底部工具栏精化**（2026-02-27）：3 档位响应式 action 布局；关注按钮延迟显示（3/5s）+ 已关注即时显示；AnimatedSize 从右滑入动画；文字压缩策略；ShaderMask 固定像素渐变遮挡；数字 `_formatCount` 统一格式；更多按钮开帖级操作面板（不接助手）。
  - **美图水平翻页修复**（2026-02-27）：GestureDetector + NeverScrollableScrollPhysics + IgnorePointer 组合，图片可水平滑动。
  - 作品指标：按当前作品显示内部 `current/total`（图组、文章卡片、视频合集）。
  - 文章阅读：封面页 + 横向卡片阅读页；mock 支持多卡片与 `full/half/third` 布局。
  - 微趣基础：微博风格卡片、图片宫格、5 行截断展开。
  - **微趣操作栏一致性**（2026-02-27）：操作图标/顺序/间距与作品频道完全对齐（赞/分享/收藏/评论，spaceBetween），数字格式同作品。

- **未完成（待后续）**
  - works-feed 服务端混排契约（当前仍为端侧临时混排）。
  - ArticleBlock metadata/codegen 正式化（当前先用 `cards` 过渡结构）。
  - 视频真实自动播放链路与音量淡入（当前为视觉占位态）。
  - 双列瀑布流模式与完整旅程/契约测试补齐。
