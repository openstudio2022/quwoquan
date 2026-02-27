# dual-rail-discovery-redesign 任务清单

## 当前交付任务

> 执行顺序：metadata → codegen → 业务逻辑 → 测试

### 阶段一：契约基础（前置，阻塞后续）

- [ ] **M1** 新增 `works-feed` API 契约到 `contracts/metadata/content/service.yaml`（`works-unified-feed` 负责）
- [ ] **M2** 新增 `ArticleBlock` 多态 schema 到 `contracts/metadata/content/fields.yaml`（`article-rich-content-blocks` 负责）
- [x] **M3** 新增 `AppArticleColors` 色彩常量到 `lib/core/theme/`，新增 `worksThemeData` 到 `lib/core/theme/`（已通过 `AppColors` 增补 `works*` 色彩常量落地）
- [ ] **M4** 注册思源宋体到 `pubspec.yaml` + `assets/fonts/source_han_serif/`
- [ ] **C1** `make verify` → `make codegen` → `make codegen-app`（生成 works-feed DTO + ArticleBlock DTO）

### 阶段二：场景切换与双轨骨架

- [ ] **B1** 扩展 `videoForceDarkProvider` → `worksForceDarkProvider`（`lib/ui/discovery/providers/`）
- [x] **B2** 重构 `DiscoveryPage`：主 Tab `[微趣][作品]`，400ms 关灯/开灯 TweenAnimationBuilder（已完成主 Tab 居中和作品模式视觉切换，400ms 过渡待精调）
- [x] **B3** 新建 `WorksImmersiveViewer`（垂直 PageView，强制分页，加载 works-feed）（已完成组件落地与交互框架；当前 works feed 仍为本地混排）
- [x] **B4** 新建 `MomentSocialFeed`（单列信息流基础版，调用 moment category feed）

### 阶段三：作品各类媒体

- [x] **W1** `PhotoGalleryItem`：水平 PageView 多图翻页，环境色模糊背景，蓝色进度条
- [ ] **W2** `VideoAutoPlayItem`：全屏自动播放，音量 500ms 淡入，水平滑系列/集合卡（当前为静态封面 + 自动播放视觉提示，真实播放链路待接入）
- [x] **W3** `ArticleCardItem`：封面模式（magazine cover），水平卡片分页，块渲染（已完成封面+卡片阅读落地；富文本 metadata 仍待）
- [x] **W4** `WorksTabFilter`：二级 Tab，1.5s 收起动画，Elastic 弹性展开，筛选参数化
- [x] **W5** `WorksGlassDrawer`：右侧 40% BackdropFilter Drawer，slide-in 动画

### 阶段四：微趣社交流完善

- [x] **Mo1** `MomentImageGrid`：1/2/3-9 图自适应宫格（微博规则），轻量图片浏览器
- [x] **Mo2** `MomentTextCard`：5 行 maxLines 截断，就地展开（本地 `_expanded` 状态）
- [ ] **Mo3** `MomentVideoCard`：`VisibilityDetector` 入焦 ≥ 60% 自动播放，音量淡入，小窗播放（当前为视频卡片预览态）
- [ ] **Mo4** 双列瀑布流切换按钮（SliverMasonryGrid，图片 8px 圆角）

### 阶段五：点位评论 UI（P1）

- [x] **An1** `WorksAnnotationDot`：GestureDetector 长按 500ms 监听，锁定 PageView
- [x] **An2** 克莱因蓝脉冲光点（ScaleTransition + AnimatedOpacity），`Stack` + `Positioned`
- [x] **An3** 点击光点打开 `WorksGlassDrawer`，松手/取消 → 200ms 淡出，解锁 PageView

### 阶段六：测试

- [ ] **T1** Widget test：双轨切换主题（ `worksForceDarkProvider` 状态正确）
- [ ] **T2** Widget test：垂直分页 + 加载更多追加
- [ ] **T3** Widget test：Tab 1.5s 收起，弹性展开，筛选重新加载
- [ ] **T4** Widget test：美图水平翻页，进度条页码
- [ ] **T5** Widget test：文章封面 → 卡片翻页
- [ ] **T6** Widget test：微趣图片宫格（各 n 图布局），文字截断展开
- [ ] **T7** Journey test：Mock 数据 works-feed 全链路（PhotoPost / VideoPost / ArticlePost 各一条）
- [ ] **T8** Contract test：works-feed API 响应结构，ArticleBlock DTO 字段一致性
- [ ] **T9** `make gate` 通过

## 当前实现同步（2026-02-27）

### 已完成（端侧）
- **双轨骨架**：`DiscoveryPage` 主 Tab 居中化（微趣/作品），400ms 关灯/开灯场景切换动画基础版。
- **作品沉浸容器**：垂直分页浏览、右侧毛玻璃评论抽屉、长按蓝色光点评论入口、顶部/底部工具栏固定悬浮。
- **作品底部工具栏精化**（2026-02-27 新增）：
  - 3 档位响应式布局（compact/regular/expanded），action 位置在同设备上跨作品严格固定。
  - 关注按钮延迟显示（图片 3s / 视频&文章 5s），已关注即时显示，从操作区左侧方向 AnimatedSize 动画滑入。
  - 文字压缩策略：关注按钮出现时 AnimatedDefaultTextStyle 缩小字号（14→12px / 10→9px）；已关注不压缩。
  - 名字渐变遮挡：ShaderMask 固定 18px 淡出（非百分比），代替硬截断"..."。
  - 数字格式化统一：`_formatCount`（<1万原值 / 万级 m.n万+ / ≥10万 显示10万+）。
  - 一级 Tab 字号与间距响应式（3 档位）。
  - 更多按钮打开帖级操作面板（3 组卡片：正向操作/反馈/取消），不打开助手。
- **作品内部指示器**：当前作品内部进度（图组 current/total、文章 1/N、视频合集 current/total）。
- **美图水平翻页修复**：顶层 GestureDetector 处理水平拖拽，内层 PageView NeverScrollableScrollPhysics，渐变层 IgnorePointer。
- **微趣社交流精化**（2026-02-27 新增）：
  - `_ActionRow`（moment_social_feed.dart）顺序与图标与作品频道完全一致（赞/分享/收藏/评论，spaceBetween）。
  - `_MomentPostCard`（discovery_page.dart）同步对齐。
  - 数字格式化同作品频道 `_formatCount` 逻辑。
- **文章 mock 与详情阅读**：mock `cards` 多卡片数据、详情页封面+横向卡片阅读、`full/half/third` 布局渲染。
- **设计系统增补**：`AppTypography.xxs = 9.0`；`UITextConstants` 新增多项（savePhoto / saveVideo / savePost / savedLabel / notInterested）。

### 仍待完成
- works-feed 服务端混排契约（`M1 / C1`，当前端侧临时混排）。
- ArticleBlock metadata/codegen 正式化（`M2 / C1`，当前用 `cards` 过渡结构）。
- 真实视频自动播放链路与音量淡入（`W2 / Mo3`，当前视觉占位态）。
- 双列瀑布流切换（`Mo4`）。
- 旅程测试与契约测试补齐（`T7 / T8`）。
- P2 点位评论坐标持久化（搁置，等待评论服务扩展）。

---

## 搁置任务（带规划）

| 任务 | 搁置原因 | 计划重启条件 | 承接节点 |
|------|----------|--------------|----------|
| **P2 点位评论坐标持久化** | 评论服务 API 尚未扩展，`Comment` 模型缺少 `position_x/y` 字段 | `publish-comment-reaction` 中评论模型扩展完成后 | `works-annotation-dot`（P2 任务） |
| **文章客户端文字分页** | Flutter `RenderParagraph` metrics 分页稳定性待评估；屏幕尺寸/字体缩放影响复杂 | 服务端预切（P1）交付后，若用户反馈需更精细排版 | `article-magazine-cover`（演进任务） |

---

## 未来演进任务

- [ ] 接入推荐排序信号（依赖 `feed-orchestration-recommendation/personalized-ranking`）
- [ ] 作品流 A/B 混排策略实验支撑（需后端实验平台）
- [ ] 双列瀑布流模式 UI 精细化（用户反馈驱动，当前交付单列基础版）
- [ ] 微趣转发到作品流的平滑过渡动效（跨轨道导航）
