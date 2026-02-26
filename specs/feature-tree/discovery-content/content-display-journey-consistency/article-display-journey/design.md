# article-display-journey 设计

## 设计动因

文章详情页与图片/视频浏览器形态不同（无左右滑动），但数据源一致、状态跨页面同步、重入保持的模式相同。按 category=article 独立实现。

## 关键决策

- **DiscoveryFeedProvider**：增加 category=article
- **路由传参**：文章详情页从 route.extra 或 feed 接收 post
- **状态**：复用 HomeState
- **无滑动**：文章为单页详情，无左右滑动、无加载更多（列表分页由 feed 控制）

## 适用场景与约束

同 spec。可待图片、视频完成后实现。
