# 开发任务：video-display-journey

## 单一数据源（已完成）

- [x] D1：DiscoveryFeedProvider 增加 category=video
- [x] D2：视频 MediaViewerPage 从 route.extra 接收 posts + initialIndex
- [x] D3：视频卡片点击传入真实 index
- [x] D4：作者详情同源
- [x] D12：视频浏览器滑动顺序 = 视频频道 feed 顺序
- [x] D14：滑动到底加载更多

## 状态同步与重入（已完成）

- [x] D5：视频浏览器注入 followingUsers
- [x] D6：视频浏览器注入赞/收藏/评论数/转发
- [x] D9：作者详情关注变更返回同步
- [x] D10：全链路 HomeState
- [x] D11：重入状态保持

---

## DTO 集成（依赖 feed-item-dto-contract 类型化 DTO 拆分完成后执行）

- [ ] D19：视频频道卡片改用 `VideoPostDto` 字段（`dto.thumbnailUrl`、`dto.durationMs`、`dto.width`、`dto.height` 等），删除旧 `Map<String, dynamic>` 取值；视频分辨率直接由 `dto.width`/`dto.height` 获取
- [ ] D20：`ImmersiveVideoViewer` 构造函数参数改为接收 `VideoPostDto`（取代原来分散的离散参数），内部直接读 `dto.xxxx`
- [ ] D24：`lib/ui/discovery/widgets/video_feed_view.dart` 新建（从 `discovery_page.dart` 抽取视频 Tab 全屏 PageView 渲染，接收 `List<VideoPostDto>`）

---

## Intent 集成（依赖 content-action-intent-contract 完成后执行）

- [ ] D21：`ImmersiveVideoViewer` 点赞 → `ref.read(contentIntentProvider).like(dto.id)`，删除 callback
- [ ] D22：`ImmersiveVideoViewer` 收藏 → `ref.read(contentIntentProvider).save(dto.id)`，删除 callback
- [ ] D23：`ImmersiveVideoViewer` 关注/取消关注 → `ref.read(userIntentProvider).follow/unfollow(dto.authorId)`，删除 callback

---

## Mock/Remote 切换

- [ ] D17：Settings 页面增加 Mock/Remote 切换开关（Developer Settings）
- [ ] D18：切换为 Remote 后视频旅程全链路正确（`RemoteContentRepository` + `VideoPostDto.fromMap` 解析）

---

## 搁置任务（带规划）

| 任务 | 搁置原因 | 计划重启条件 |
|------|----------|-------------|
| 跨进程状态持久化 | 依赖云侧 API | content-action-intent-contract 完成后 |

---

## 未来演进任务

- 视频预加载策略（相邻 ±1 视频预缓冲）
- 视频播放进度上报（BehaviorRepository.track）
