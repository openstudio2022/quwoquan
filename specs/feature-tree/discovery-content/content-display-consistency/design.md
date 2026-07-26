# L2 Design：内容展示一致性 (`content-display-consistency`)

> 对应规格：[L2 spec](./spec.md)

> 设计触发原因：“统一文章、圈子流、沉浸式浏览器与作者主页之间的展示和状态交接”需要 `article-display-journey`、`circle-feed-viewer-handoff-contract`、`content-action-intent-contract`、`feed-item-dto-contract`、`moment-display-journey`、`photo-display-journey`、`video-display-journey`、`viewer-profile-state-sync-contract` 共享状态 owner、契约或质量边界。

## 1. 背景、目标与非目标

- 设计目标：统一文章、圈子流、沉浸式浏览器与作者主页之间的展示和状态交接。
- 非目标：复制字段 schema、实现任务、测试排列组合或执行历史。

## 2. Story 协作与状态流

- [`article-display-journey`](./article-display-journey/spec.md)：整个卡片为统一热区，点击直接进入文章沉浸式阅读器。
- [`circle-feed-viewer-handoff-contract`](./circle-feed-viewer-handoff-contract/spec.md)：圈子 post 进入 viewer 时必须传入。
- [`content-action-intent-contract`](./content-action-intent-contract/spec.md)：更多操作面板只展示已具备真实结果或安全终态的能力；禁止“功能开发中”假入口。
- [`feed-item-dto-contract`](./feed-item-dto-contract/spec.md)：`generated/content/feed_item_dto.g.dart` 标记 `// Code generated ... DO NOT EDIT.`，禁止手改。
- [`moment-display-journey`](./moment-display-journey/spec.md)：**行为基线**：作品侵入式浏览器作为统一行为基线；微趣点击图片/视频后进入同等交互能力的侵入式浏览器。
- [`photo-display-journey`](./photo-display-journey/spec.md)：让图片频道、沉浸式浏览器与作者主页使用同一内容身份和互动状态，并在返回时保持上下文。
- [`video-display-journey`](./video-display-journey/spec.md)：首页/视频频道/作品浏览器的同一视频 post 未播放态封面一致，点击后能进入同一 `videoUrl` 的播放态。
- [`viewer-profile-state-sync-contract`](./viewer-profile-state-sync-contract/spec.md)：viewer、profile 与 feed 消费同一 canonical `RelationshipCapabilityView` 关系矩阵。

## 3. 端云与数据流

- 上游能力：[`discovery-content`](../spec.md) 声明的领域入口。
- 下游能力：本目录直接 Story 及其公开结果。
- 一致性要求：遵循本层或父 L1 DEC 声明的一致性边界。

## 4. 关键决策

<a id="dec-001"></a>
### DEC-001 列表、沉浸浏览器与作者主页共享对象身份和互动状态
- 决策：列表、沉浸浏览器与作者主页共享对象身份和互动状态。
- 理由：统一文章、圈子流、沉浸式浏览器与作者主页之间的展示和状态交接。
- 被否决方案：由调用方、页面或脚本复制本层状态并绕过公开契约。
- 约束与影响：实现只能细化对应规格与 canonical contract；冲突时先修正规格或契约。
- 关联要求：`REQ-001`
- 影响 Story：[`article-display-journey`](./article-display-journey/spec.md)、[`circle-feed-viewer-handoff-contract`](./circle-feed-viewer-handoff-contract/spec.md)、[`content-action-intent-contract`](./content-action-intent-contract/spec.md)、[`feed-item-dto-contract`](./feed-item-dto-contract/spec.md)、[`moment-display-journey`](./moment-display-journey/spec.md)、[`photo-display-journey`](./photo-display-journey/spec.md)、[`video-display-journey`](./video-display-journey/spec.md)、[`viewer-profile-state-sync-contract`](./viewer-profile-state-sync-contract/spec.md)
- 关联验收：`SIT-001`

## 5. 失败与恢复

- 失败类型：权限拒绝、依赖超时、版本冲突或持久化失败。
- 可见结果：调用方收到可区分的 canonical failure 或规格明确允许的降级结果；任何失败均不写入成功事实。
- 恢复动作：调用方按 canonical recovery action 重试、刷新或停止；不得自行合成成功结果。
- 禁止 fallback：不得回退到 Mock、旧 wire、双读双写或页面本地写副本。

## 6. 质量与观测

- 无法优雅承接 outbox 与系统级配置。
- 本地默认值来自 codebase，远端配置只做覆盖。
- `GetAppConfig` 扩展 `client_state_sync` 配置输出结构。
- feature flag、观测、SLO 验证与回滚。
