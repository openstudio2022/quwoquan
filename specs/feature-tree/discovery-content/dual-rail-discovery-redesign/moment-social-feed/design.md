# moment-social-feed 设计

## 设计动因
微趣轨需要"快、密、互动"——与作品轨的沉浸慢读形成对比。微博式布局已被用户高度熟悉，降低认知负担；双列瀑布流提升信息密度，适合快速浏览。

## 适用场景与约束
适用：微趣频道，跟随系统主题（明亮）。约束：与作品轨完全隔离，不共享深色主题逻辑。

## 关键决策
- 单列：`ListView.builder`，每条 `MomentPostCard`
- 双列：`CustomScrollView` + `SliverMasonryGrid`（`flutter_staggered_grid_view` 包），`crossAxisCount: 2`
- 切换按钮：顶部右侧图标，`ValueNotifier<bool> _isWaterfall` 本地状态

## 操作栏一致性设计

微趣与作品频道的操作栏对齐，消除用户的跨轨认知差：

**统一顺序**：赞 · 分享 · 收藏 · 评论（从左到右）

**统一图标集**：
| 操作 | 图标 | 激活色 |
|------|------|-------|
| 赞 | `CupertinoIcons.heart` / `heart_fill` | `AppColors.worksLike` |
| 分享 | `CupertinoIcons.arrowshape_turn_up_right` | — |
| 收藏 | `CupertinoIcons.star` / `star_fill` | `AppColors.warning` |
| 评论 | `CupertinoIcons.chat_bubble` | — |

**间距策略**：`Row(mainAxisAlignment: MainAxisAlignment.spaceBetween)` 等间距，适配不同卡片宽度，无需硬编码像素。

**数字格式**：与作品频道 `_formatCount` 完全一致。

**方案对比**：

| 方案 | 描述 | 选用原因 |
|------|------|---------|
| **A（选定）等间距 + 作品图标集** | 4 个 chip spaceBetween，图标与作品一致 | 跨轨道认知一致性高 |
| B 旧实现（赞/藏/评 + Spacer + 分享） | 分享居右独立，其余左对齐 | 顺序与作品不一致，分享被边缘化 |

## 未来演进
- 无限滚动预加载（当前基础版）
- 微趣 → 作品平滑过渡动效（跨轨道导航）
