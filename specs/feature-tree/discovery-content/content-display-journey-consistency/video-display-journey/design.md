# video-display-journey 设计

## 设计动因

与 photo-display-journey 模式一致，视频频道与视频浏览器需单一数据源、状态跨页面同步、重入保持。按 category=video 独立实现，不与图片混用。

## 关键决策

- **DiscoveryFeedProvider**：增加 category=video，与 photo 隔离
- **路由传参**：视频 MediaViewerPage 从 route.extra 接收 posts + initialIndex
- **状态**：复用 HomeState，与图片共用
- **滑动**：与图片浏览器同模式，滑动到底加载更多
- **AuthorProfile**：与图片共用，数据同源

## 适用场景与约束

同 spec。依赖 photo-display-journey 先完成，复用 DiscoveryFeedProvider 模式。
