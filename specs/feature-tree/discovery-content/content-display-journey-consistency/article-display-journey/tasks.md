# 开发任务：article-display-journey

> 2026-03-22 更新：以下任务基于旧版“文章详情页”假设，已不再对应最新 `/prd`。进入 `/design` 后必须按新的文章分发卡 / 沉浸式阅读器 / 编辑态模板体系重建任务清单。

## 单一数据源

- [ ] D1：DiscoveryFeedProvider 增加 category=article
- [ ] D2：文章详情页从 route.extra 或 feed 接收 post
- [ ] D3：文章卡片点击传入 index 或 route 参数
- [ ] D4：作者详情同源

## 状态同步与重入

- [ ] D5：文章详情注入 followingUsers
- [ ] D6：文章详情注入赞/收藏/评论数/转发
- [ ] D9：作者详情关注变更返回同步
- [ ] D10：全链路 HomeState
- [ ] D11：重入状态保持
