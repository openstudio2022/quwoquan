# moment-display-journey 设计

## 设计动因

微趣旅程与图片/视频模式一致（可能有浏览器形态或详情页）。按 category=moment 独立实现，数据源一致、状态跨页面同步、重入保持。

## 关键决策

- **DiscoveryFeedProvider**：增加 category=moment
- **路由传参**：微趣详情/浏览器从 route.extra 接收 posts + initialIndex（形态待定）
- **状态**：复用 HomeState
- **形态**：微趣详情或浏览器形态待产品确定，可复用图片/视频模式

## 适用场景与约束

同 spec。可待图片、视频、文章完成后实现。
