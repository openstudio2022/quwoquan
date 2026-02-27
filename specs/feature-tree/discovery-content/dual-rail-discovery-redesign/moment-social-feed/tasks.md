# moment-social-feed 任务清单

## 当前交付任务
- [x] **Mo1** 新建 `MomentSocialFeed`（`lib/ui/discovery/widgets/moment_social_feed.dart`）
- [x] **Mo2** 单列 `ListView.builder`，接入 `discoveryFeedProvider(tabId: 'moment')`
- [ ] **Mo3** 顶部切换按钮：单列/双列，`ValueNotifier<bool> _isWaterfall`
- [ ] **Mo4** 双列模式：`SliverMasonryGrid.count(crossAxisCount: 2)`，图片 `borderRadius: 8`
- [x] **T1** Widget test：`MomentPostDto` 各类型（纯文/图/视频）正确渲染（通过 discovery feed widget 回归）

### 操作栏一致性精化（已完成）
- [x] **Mo5** `_ActionRow`（`moment_social_feed.dart`）顺序与作品频道一致：**赞 · 分享 · 收藏 · 评论**；`Row(mainAxisAlignment: MainAxisAlignment.spaceBetween)` 等间距布局
- [x] **Mo6** 图标与作品频道一致：`CupertinoIcons.heart`/`heart_fill`、`arrowshape_turn_up_right`、`star`/`star_fill`、`chat_bubble`；激活色：赞用 `AppColors.worksLike`，收藏用 `AppColors.warning`
- [x] **Mo7** 数字格式化 `_fmt`（同作品频道 `_formatCount` 逻辑）：< 10 000 原值，万级 `m.n万+`，≥ 10万 显示 `10万+`
- [x] **Mo8** `_MomentPostCard`（`discovery_page.dart`）同步以上三项改动，保持两处微趣卡片实现一致

> L4 子节点各自有独立 tasks。

## 搁置任务（带规划）
暂无。

## 未来演进任务
- [ ] 微趣 → 作品平滑过渡动效
- [ ] 视频 `VisibilityDetector` 入焦自动播放（当前为视频卡片预览态）
