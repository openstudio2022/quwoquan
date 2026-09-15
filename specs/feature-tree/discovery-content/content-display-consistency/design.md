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
- 图片/视频及图片静态页/翻页纹理复用 [双轨发现 DEC-003](../dual-rail-discovery-redesign/design.md#dec-003) 的单一整栏几何；比例与显示窗口只消费 [works-immersive-viewer REQ-024](../dual-rail-discovery-redesign/works-immersive-viewer/spec.md#req-024)，不另建连续侵入栏内、无条件 cover 或图片专用 contain 主线。竖屏视频拖动控制与 chrome 共享同一 `VideoPlaybackSnapshot.isScrubbing`：caption、居中全屏入口及 association slot 同步退出绘制、命中和 semantics，保留测量空间，档位、对称裁剪和媒体矩形不跳动；不存在独立 current-time 行或时间锚点。timeline 仅持有手势热区和虚拟 target，视觉轨保持贴底基准并在增厚时向上展开；释放只提交一次 seek，取消不提交，两者保留 session intent。播放中的 scrub 不暂停或额外续播，取消保留自然推进的最新实际位置，paused 仍取原稳定位置；清除虚拟 target 后继续有效播放计时，不由可视层发第二套 play/pause/seek。竖屏 30 秒边界及 inlineFeed 的独立规则仅引用 [video-display-journey REQ-004](./video-display-journey/spec.md#req-004)。
- 横向几何以 `safeViewportRect -> fixed left/right control slots + mediaStageRect -> contained visibleMediaRect` 单向派生；外槽只随视口/安全区变化，标题、时间轴、作者/关注、赞转评只消费实际媒体像素左右边界，中央按钮只消费实际媒体中心。时间轴视觉端点按 thumb 半径内缩，横向任何 chrome 不再从整视口或固定 inset 平行推导。显隐使用始终挂载的 interaction plane，pointer-down 固定起始显隐意图；普通 hold 与 require-visible blocker 分型，session position tick 不得因 held pointer 强制 reveal 或销毁 gesture arena 参与者；隐藏短点只 reveal，横向播放 intent 仅由显示后的中央按钮改变。
- 横向展示与恢复复用 [双轨发现 DEC-004](../dual-rail-discovery-redesign/design.md#dec-004) 的 viewer 局部旋转和单一控件显隐状态机，不请求/捕获/恢复系统方向、不复制播放器或进入时旧播放位置。标题在顶部，作者/关注与赞转评保留底部分组；视频所有已知有效时长的时间轴位于整组上方，时间只在 scrub 显示，图片无播放/时间轴。播放、暂停和图片统一五秒隐藏全部普通控件（含退出），slot 与短视频 timeline 不另设竞争 timer；viewer 画布层以幂等 reveal/hide、pointer identity、blocker 集合及绑定 post/media/session 的独立 chrome epoch 协调拖动、按住、弹层、路由、buffering/loading/failure 等挂起条件，轻点只显隐，迟到回调不可改写新交互。横向禁切作品/翻图/切集，作者/评论往返与收起消费同一媒体最新位置/intent 和互动状态；主壳导航在整个沉浸周期保持隐藏。功能验收直接绑定 [GWT-021](../dual-rail-discovery-redesign/works-immersive-viewer/spec.md#gwt-021)、[GWT-023](../dual-rail-discovery-redesign/works-immersive-viewer/spec.md#gwt-023)、[GWT-024](../dual-rail-discovery-redesign/works-immersive-viewer/spec.md#gwt-024) 与 [GWT-025](../dual-rail-discovery-redesign/works-immersive-viewer/spec.md#gwt-025)，本层不维护第二套模式/失败恢复合同。
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
