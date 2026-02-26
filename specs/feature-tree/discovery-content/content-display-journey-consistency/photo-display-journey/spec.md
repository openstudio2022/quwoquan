# L3 特性：photo-display-journey（图片旅程）

## 功能说明

**图片独立旅程**：美图频道 → 图片沉浸式浏览器 → 作者详情，端到端数据源一致、交互状态跨页面同步、重入状态保持。

- **数据源**：列表、浏览器、作者详情共用同一 feed（category=photo）
- **展示**：浏览器展示与 post 一致（作者、关注、赞、收藏、评论数、转发、多图、文字）
- **状态**：关注/赞/收藏跨页面同步；作者详情关注变更返回后同步；退出再进状态保持
- **滑动**：左右滑动顺序与美图频道 feed 一致；多图 post 内滑动；滑动到底加载更多

## 适用范围与约束

- **适用**：发现页美图频道；图片沉浸式浏览器（ImmersiveImageViewer）；作者详情（AuthorProfile）
- **约束**：须支持 Mock/Remote 一键切换；按 category=photo 隔离数据源

## 与父/子节点关系及依赖

| 依赖节点 | 关系 | 说明 |
|----------|------|------|
| `feed-item-dto-contract`（L3，并列） | **前置依赖** | D19/D20 任务须在 feed-item-dto-contract 完成后执行 |
| `content-action-intent-contract`（L3，并列） | **前置依赖** | D21/D22/D23 任务须在 content-action-intent-contract 完成后执行 |
| `content-display-journey-consistency`（L2） | 父节点 | |

## 验收

- A1：列表、浏览器、作者详情数据与 post 一致，均使用 `FeedItemDto` 规范字段
- A2：关注/赞/收藏跨页面一致，重入后保持；HomeState 为唯一状态源
- A3：作者详情关注/取消后返回，浏览器展示自动更新（共享 homeStateProvider）
- A4：浏览器滑动顺序与列表一致，支持加载更多
- A5：`ImmersiveImageViewer` 无 `onLikeClick`/`onSaveClick`/`onFollowClick` callback，使用 Intent Provider
- A6：Mock/Remote 切换后全链路正确
- A7：`FeedItemDto` 字段与 metadata 一致（依赖 feed-item-dto-contract A1~A8）
