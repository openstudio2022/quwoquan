# L2 特性：content-display-journey-consistency

## 功能说明

发现流 → 各类型浏览器/详情 → 作者详情的端到端用户旅程中，**数据源一致**、**字段规范统一**、**交互状态跨页面同步**、**重入状态保持**、**写操作乐观更新并异步云侧回写**。

**四类内容各自独立旅程**：图片（photo）、视频（video）、文章（article）、微趣（moment）分别有独立的列表 ↔ 浏览器/详情 ↔ 作者详情 旅程，按 category 隔离数据源与路由，互不混用。当前优先实现**图片旅程**及其基础层（DTO 契约 + 操作意图契约）。

## 范围

- **数据源**：每类旅程内，列表、浏览器、作者详情共用同一 feed/post 数据
- **字段规范**：`FeedItemDto`（codegen，由 `feed-item-dto-contract` 提供）作为端侧唯一 DTO，消除字段别名兜底链
- **展示一致性**：浏览器展示（作者、关注、赞、收藏、评论数、转发、多图、文字）与 post 一致
- **状态同步**：关注/赞/收藏在列表、浏览器、作者详情间一致；作者详情关注变更返回后同步到浏览器
- **重入保持**：退出浏览器回到频道、再次进入时，关注/赞/收藏状态保持一致
- **写操作**：赞/收藏/关注通过 Intent 层乐观更新，异步触发云侧 API（由 `content-action-intent-contract` 提供）
- **滑动顺序**：浏览器左右滑动顺序与列表一致；支持加载更多
- **四类独立**：图片、视频、文章、微趣各自独立实现，复用模式但按 category 隔离

## 适用范围与约束

- **适用**：发现页四类频道（美图、视频、文章、微趣）；对应类型浏览器/详情；作者详情
- **当前范围**：优先**DTO 基础层**（`feed-item-dto-contract`）→ **操作意图层**（`content-action-intent-contract`）→ **图片旅程**（`photo-display-journey`）；视频、文章、微趣各自独立扩展
- **不适用**：圈子流等其他 feed 来源
- **约束**：须支持 Mock/Remote 一键切换，所有 Repository 遵守 `appDataSourceModeProvider`；`FeedItemDto` 字段变更走 metadata → codegen 流程，禁止手改 generated 文件

## 与父/子节点关系

**两层基础 + 四类媒体旅程**，执行顺序为：基础层先行，旅程层依赖基础层。

| 子节点 | 职责 | 优先级 |
|--------|------|--------|
| **feed-item-dto-contract** | 规范 DTO：metadata codegen `FeedItemDto`，mock 数据迁移，Repository 输出类型化 DTO，消除别名链 | **优先（前置）** |
| **content-action-intent-contract** | 操作意图：like/save/follow 乐观更新 + 云侧回写，`UserRepository` 补全 follow API | **优先（前置）** |
| photo-display-journey | 图片旅程：美图频道 ↔ 图片浏览器 ↔ 作者详情；依赖上两个 L3 | **优先** |
| video-display-journey | 视频旅程：视频频道 ↔ 视频浏览器 ↔ 作者详情 | 二期 |
| article-display-journey | 文章旅程：文章频道 ↔ 文章详情页 ↔ 作者详情 | 二期 |
| moment-display-journey | 微趣旅程：微趣频道 ↔ 微趣详情/浏览器 ↔ 作者详情 | 二期 |

## 验收标准概要

- A1：列表、浏览器、作者详情数据与 post 一致，均使用 `FeedItemDto` 规范字段
- A2：关注/赞/收藏跨页面一致，重入后保持；`HomeState` 为唯一状态源
- A3：作者详情关注/取消后返回，浏览器展示更新
- A4：浏览器滑动顺序与列表一致，支持加载更多
- A5：赞/收藏/关注操作乐观更新，失败回滚；不再使用 callback 链
- A6：Mock/Remote 切换后全链路正确
- A7：`FeedItemDto` 字段与 `discovery_feed.yaml` metadata 一致，`make gate` 通过
- A8：mock/unit/contract/integration 测试覆盖上述场景
