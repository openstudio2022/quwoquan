# content-display-journey-consistency 设计方案

## 设计动因

当前内容展示链路的主要问题已经从“列表与浏览器不同源”升级为“多来源、多对象、多状态模型并存”：

1. discovery 与 circle 两类来源进入 viewer 的 handoff 结构不一致，导致圈子来源缺正文、缺完整互动快照、返回后只回写局部数字。
2. profile 已冻结 `RelationshipCapabilityView` 作为按钮矩阵真相源，但 viewer / feed 仍在混用 `isFollowing`、`followingUsers`、`userId`、`authorId` 等局部状态。
3. 现有点击行为多为“立即发请求”，对弱网、反复点击、重入恢复和系统级灰度不友好。

本设计的核心目标是把 `feed -> immersive viewer -> author profile -> return` 的旅程，统一到一套可演进的对象模型、状态同步模型和运行时同步模型上。

## 上游输入评审

| 输入 | 当前结论 |
|------|----------|
| `content-display-journey-consistency/spec.md` | 已冻结 discovery + circle 统一旅程、对象级真相源、`sys.client_state_sync.*`、灰度回滚口径，可进入 `/design` |
| `content-display-journey-consistency/acceptance.yaml` | `J1/J2/J3/R1` 已按 Journey schema 冻结，足以承载 plan slices |
| `viewer-profile-state-sync-contract/spec.md` | 已明确 canonical key、shared provider、outbox 聚合同步是本次核心 Scenario |
| `circle-feed-viewer-handoff-contract/spec.md` | 已明确 circle 正式纳入范围，且只作为来源上下文，不自持第二套状态真相 |
| `content-action-intent-contract/spec.md` / `design.md` | 已冻结 like/favorite/share/comment/report/block 的 intent 边界，可复用为 viewer/feed/profile 的写入基础 |
| `owner-subaccount-homepage-unification` | 已冻结 `SubAccountProfileView` 与 `RelationshipCapabilityView`，本次不再重定义 profile 关系矩阵 |
| 现状代码 | `MediaViewerExtra` / `MediaViewerResult` 已存在；`section_creations.dart` 的圈子 handoff 仍不完整；`profile_state_provider.dart` 仍以 `isFollowing` 为主；`discovery_state.dart` 仍是旧的页面内状态容器 |

结论：

- `/design` 准入满足。
- 需要把旧 L2 设计中 `DiscoveryFeedProvider + HomeState` 的单来源思路，升级为 `canonical projection + shared provider + handoff contract + outbox`。
- 本次设计涉及 metadata / codegen，已实际执行 `make -C quwoquan_service verify-metadata && make codegen && make codegen-app`，当前仓库基线通过。

## 对标输入分析

### 外部对标

| 对标对象 | 吸收点 | 不吸收点 |
|----------|--------|----------|
| 小红书 | 内容流进入作者页后返回不闪烁收敛；圈层来源与推荐来源进入详情的行为一致 | 不照搬其 feed 对象模型 |
| 抖音 | viewer 与作者页切换的即时反馈、状态连续感 | 不照搬其单轨视频 IA |
| 微博 | 多来源进入详情页后互动语义一致 | 不照搬其弱关系图谱与页面编排 |

### 内部对标

| 文档 / 能力 | 可复用点 |
|-------------|----------|
| `content-action-intent-contract` | 乐观更新、专用路由与批量行为边界、失败回滚基础 |
| `owner-subaccount-homepage-unification` | `SubAccountProfileView` / `RelationshipCapabilityView` 与 profile 按钮矩阵 |
| `feed-item-dto-contract` | content projection codegen 与 DTO 统一出口 |
| `contentRuntimeConfigProvider` | 现有 app config 拉取与 feature flag 合并机制，可扩到 sync 参数 |

## 方案对比

### 方案 A：以 route result 为主的页面级同步

核心思路：

- viewer、profile、feed 各自维护本地状态。
- 页面跳转时通过 `MediaViewerExtra` / `MediaViewerResult` / `UserProfileRouteExtra` 传递快照。
- 返回时由上游页面手动吸收结果。

优点：

- 对现有页面改动最小。
- 不需要引入新的全局状态中心。

缺点：

- 状态真相源仍分散，重入、多实例、弱网失败场景容易漂移。
- discovery 与 circle 很容易各演化出一套吸收逻辑。
- 无法优雅承接 outbox 与系统级配置。

### 方案 B：纯 shared provider，同步完全不依赖 route result

核心思路：

- feed / viewer / profile 只 watch 共享 provider。
- route extra 仅传最小标识，首屏缺失字段靠 viewer 自行补拉。
- 页面返回不处理显式结果。

优点：

- 真相源最单一。
- 路由层最干净。

缺点：

- 首屏需要额外补拉数据，圈子来源会出现“先空后有”。
- 当来源侧需要吸收来源上下文时，缺少明确 return contract。
- 对当前 viewer / circle 入口的迁移跨度过大。

### 方案 C：共享 provider 为主、handoff/result 为补强、outbox 负责延迟批同步

核心思路：

- `MediaViewerExtra` 负责首屏完整 handoff，保证 viewer 首屏不自拉。
- `UserRelationshipStateProvider` 与 `PostInteractionStateProvider` 负责长生命周期真相源。
- `MediaViewerResult` 仅作为来源页的补强吸收，不再作为唯一真相源。
- 所有写操作先更新 provider，再进入 `sync outbox`，按 `sys.client_state_sync.*` 聚合 flush / retry。

优点：

- 同时兼顾首屏完整性、跨页面一致性、重入保持与来源页回写闭环。
- 兼容 discovery 与 circle 两类来源。
- 可以在不改动外部路由形态的前提下完成 canonical key 迁移。

缺点：

- 需要同时收口 route contract、provider、outbox 与 runtime config。
- 设计和实施都比方案 A 更重。

## 选型决策

选定方案：**方案 C**

决策理由：

1. 它保留了 route handoff 对首屏完整性的价值，不会把圈子来源打回“详情页自拉数据”。
2. 它把真正的状态真相源上收到 provider，能解决多页面、多实例和重入问题。
3. 它天然适配 `10s` 批同步、`5min` 重试与系统级参数下发。

## 关键设计决策

### KD1：对象级唯一真相源

- `user` 对象负责：
  - `SubAccountProfileView`
  - `RelationshipCapabilityView`
  - follow / unfollow 的当前意图与最终收敛
- `post` 对象负责：
  - media / title / body / counters
  - like / favorite / share 的当前意图与最终收敛
- `circle` 对象只负责：
  - 来源上下文
  - 回到原来源时的列表定位与原始 raw post 映射

圈子不再维护自己的关系态真相源，也不再拥有独立的 viewer 状态协议。

### KD2：canonical key 统一与兼容迁移

- 对外路由继续使用 `app_routes.yaml` 中的 `userProfile -> /user/{username}`。
- 内部用户 key 冻结为 `ProfileSubjectId`。
- post 作者引用从 `authorId` 演进到 `authorProfileSubjectId`。
- `PostId` 作为 post interaction 的唯一 key。

兼容期规则：

- metadata / codegen 新增 `authorProfileSubjectId` 后，App 读取优先级为：
  - `authorProfileSubjectId`
  - fallback `authorId`
- `usernameSlug` 仅用于 route path，不得作为 provider state key。

### KD3：统一 handoff contract

`MediaViewerExtra` 演进为“首屏可渲染 + 来源可回写”的完整契约，至少包含：

- canonical `PostId`
- canonical `authorProfileSubjectId`
- `posts` / `dtoPosts`
- `initialIndex` / `category`
- `source`
- `circleId`（如存在）
- `rawPostsById`
- `interactionSnapshot`

`MediaViewerInteractionSnapshot` 与 `MediaViewerResult` 不再只是“数字容器”，而是来源页与 viewer 的对账补强协议：

- `followingUsers`
- `likedPosts`
- `savedPosts`
- `postLikesCount`
- `postBookmarksCount`
- `postSharesCount`

### KD4：共享 provider 拓扑

设计目标是替换当前“页面内状态容器 + callback + route result 混搭”的模式：

- `UserRelationshipStateProvider`
  - key: `ProfileSubjectId`
  - source: `RelationshipCapabilityView` + 本地 pending intents
- `PostInteractionStateProvider`
  - key: `PostId`
  - source: post projection counters + 本地 pending intents
- `ViewerSourceStateAdapter`
  - 职责：把 discovery / circle 的来源上下文转换为 `MediaViewerExtra`
- `ViewerDismissAbsorber`
  - 职责：把 `MediaViewerResult` 作为来源页补强吸收，但不反向覆盖 shared provider 的最终状态

迁移目标文件：

- `lib/core/models/media_viewer_extra.dart`
- `lib/ui/discovery/widgets/works_immersive_viewer.dart`
- `lib/ui/circle/widgets/section_creations.dart`
- `lib/ui/user/providers/profile_state_provider.dart`
- `lib/ui/discovery/providers/discovery_state.dart`

### KD5：outbox 延迟批同步模型

本次不采用“点击即请求”。

App 侧新增轻量本地同步模型，建议命名：

- `ClientStateSyncIntent`
- `ClientStateSyncOutboxEntry`
- `ClientStateSyncScheduler`

聚合规则：

- follow/unfollow：按 `ProfileSubjectId + intentType`
- like/favorite/share：按 `PostId + intentType`
- 合并策略：`latest_wins`
- outbox 为每个 key 记录“云端已确认状态 + 本地最终意图”；窗口内允许立即反向点击，若最终意图回到已确认状态，则直接删除 pending entry，不发云端持久化请求。
- 若 flush 已发出而用户又在窗口内反悔，则保留最新本地意图，并在本轮 flush 完成后基于最新 confirmed 状态继续收敛，避免 feed / viewer / profile 与云端出现断链。

调度规则：

- `flush_delay_sec` 默认 `10`
- `retry_delay_sec` 默认 `300`
- `max_batch_size`
- `max_pending_age_sec`
- `flush_on_foreground_resume`
- `flush_on_network_recovered`

失败策略：

- 本地 provider 保留最后用户意图。
- outbox 进入 retry queue。
- reconcile 成功后清除 pending。

### KD6：运行时配置与灰度

配置真相源：

- `_control_plane/platform/config_schema.yaml` 增加：
  - `sys.client_state_sync.flush_delay_sec`
  - `sys.client_state_sync.retry_delay_sec`
  - `sys.client_state_sync.max_batch_size`
  - `sys.client_state_sync.max_pending_age_sec`
  - `sys.client_state_sync.flush_on_foreground_resume`
  - `sys.client_state_sync.flush_on_network_recovered`

App 读取路径：

- 继续复用 `ContentRepository.getAppConfig()`
- 在 `ContentRuntimeConfigState.fromAppConfig()` 中新增 `client_state_sync` 段解析
- 本地默认值来自 codebase，远端配置只做覆盖

灰度开关建议：

- `ops.content.viewer_profile_state_sync_v1`
- `ops.content.circle_viewer_handoff_v1`
- `ops.content.client_state_sync_outbox_v1`

### KD7：首屏文案与 projection 一致性

viewer 不再自行推断 photo/video 文案。

为保证图片、视频、微趣的正文与首屏一致，需要：

- `PostSummaryView.fromDto()` 始终消费 DTO 中的 canonical `body`
- `MediaViewerExtra.posts` 与 `dtoPosts` 同时传入时，以 projection 为主、DTO 为补充
- circle 来源不得省略 `rawPostsById` 与正文来源映射

## metadata / codegen 方案

### 需要演进的 metadata

#### 1. `content/post`

目标：

- 为 viewer/feed/profile 统一提供 canonical 作者 key 与稳定 projection。

建议修改：

- `quwoquan_service/contracts/metadata/content/post/fields.yaml`
  - 在 post / projection 视图中新增 `authorProfileSubjectId`
- `quwoquan_service/contracts/metadata/content/post/service.yaml`
  - 保持 `GetFeed` / `GetPost` 路由不变
  - `GetAppConfig` 扩展 `client_state_sync` 配置输出结构

#### 2. `user/follow_edge`

目标：

- 直接复用 `RelationshipCapabilityView`，不再让 App 侧从 `bool` 组合推断按钮矩阵。

建议修改：

- 若现有 response_fields 缺少后续实施所需字段，仅做字段补齐，不改 operation 语义。

#### 3. `_control_plane/platform/config_schema.yaml`

目标：

- 为 `sys.client_state_sync.*` 提供正式 schema、默认值、reload 与 rollout 语义。

#### 4. `_shared/app_routes.yaml`

目标：

- 保持 `userProfile` 路由稳定，不新增第二套路由。
- viewer 路由 path 不变，handoff 结构在 `extra` 层演进。

### codegen 影响

预期会影响：

- `quwoquan_app/lib/cloud/runtime/generated/content/*.g.dart`
- `quwoquan_app/lib/cloud/runtime/generated/user/*.g.dart`
- `quwoquan_app/lib/cloud/runtime/generated/content/content_api_metadata.g.dart`
- `quwoquan_app/lib/cloud/runtime/generated/content/content_request_page_ids.g.dart`
- `generated/control_plane/platform_config_schema.go`

G1 校验结果：

- `make -C quwoquan_service verify-metadata`
- `make codegen`
- `make codegen-app`

已实际执行并通过，说明当前仓库基线健康，可在后续 `/dev` 阶段以 metadata-first 方式增量演进。

## 字段演进、迁移 / 回填、双读双写

### 字段演进

- `authorId` -> `authorProfileSubjectId`
- `isFollowing` 页面局部布尔值 -> `RelationshipCapabilityView + UserRelationshipStateProvider`
- `likedPosts/savedPosts/followingUsers` 页面内散落集合 -> shared provider + outbox

### 迁移 / 回填

- metadata phase：只声明 canonical 字段；禁止保留旧字段作为第二真相源。
- App phase：provider / DTO / UI 只认 canonical key（如 `authorProfileSubjectId`）。
- cleanup phase：`authorId` 不得再作为状态 key 或 wire 别名。

### 双读 / 双写

- **禁止 wire 双读**：不得以 `authorId` 回退补全 `authorProfileSubjectId`。
- 双写：本次不做长期双写云端实体；只做本地 pending state + 云端单真相写入

## feature flag、观测、SLO 验证与回滚

### feature flag

- `ops.content.viewer_profile_state_sync_v1`
- `ops.content.circle_viewer_handoff_v1`
- `ops.content.client_state_sync_outbox_v1`

### 观测

核心指标：

- `viewer_profile_sync_mismatch_rate`
- `circle_viewer_handoff_missing_field_total`
- `client_state_sync_outbox_pending_count`
- `client_state_sync_flush_success_rate`
- `client_state_sync_retry_success_rate`
- `client_state_sync_reconcile_mismatch_rate`

关键日志：

- source = discovery / circle
- handoff payload field completeness
- canonical key fallback hit rate
- outbox coalesce result
- flush / retry / reconcile outcome

### SLO 验证

- UI optimistic update: `p95 < 100ms`
- default flush trigger: `<= 10s`
- retry trigger: `<= 5min`
- cloud persistence convergence: `p95 < 30s`
- circle / discovery 进入 viewer 首屏不额外补拉正文

### 回滚

1. 关闭 `viewer_profile_state_sync_v1`，回退到现有页面级同步。
2. 关闭 `circle_viewer_handoff_v1`，圈子入口回退旧 viewer handoff。
3. 关闭 `client_state_sync_outbox_v1`，回退到现有直接写请求模式。
4. 保持 route path 与已有 DTO fallback，不需要做破坏性 schema 回滚。

## TDD / ATDD 策略

| 验收 | 测试层 | 设计策略 |
|------|--------|----------|
| J1 | local_contract, local_contract, api_integration, user_acceptance | discovery/circle handoff schema、widget/integration、真实旅程回归 |
| J2 | local_contract, local_contract, api_integration | canonical key、provider 边界、profile/viewer/feed 一致性 |
| J3 | local_contract, local_contract, api_integration, user_acceptance | outbox 配置 schema、coalesce/retry、弱网与恢复旅程 |
| R1 | local_contract, api_integration, user_acceptance | 灰度配置、观测 guardrail、回滚演练 |

## plan slice 与 三层测试 证据矩阵映射

| Slice | 目标 | 主要验收 | 主要证据 |
|-------|------|----------|----------|
| P1 | 冻结 canonical metadata 与 runtime config schema | J2, J3 | local_contract |
| P2 | 生成并接入 codegen 基线 | J2, J3 | local_contract, api_integration |
| P3 | 落地 shared provider 与 viewer/profile 同步 | J2 | local_contract, api_integration |
| P4 | 落地 circle handoff / dismiss absorb | J1 | local_contract, api_integration |
| P5 | 落地 outbox flush / retry / reconcile | J3 | local_contract, api_integration, user_acceptance |
| P6 | 灰度、观测与回滚验证 | R1 | api_integration, user_acceptance |

## 未来演进

- 把 discovery/circle 之外的更多来源接入统一 `ViewerSourceStateAdapter`。
- 收缩 `DiscoveryState` 这类记录页面态容器，完全迁移到对象级 provider。
- 在 metadata 稳定后移除 `authorId` 作为内部状态 key 的兼容读链路。
- 若后续需要跨进程更强保证，可把 outbox 从本地轻量持久化升级为更正式的 runtime sync queue。

## KD8：商用视频播放会话与交互状态

### 目标与范围

本决策把视频展示统一为两个、且只有两个 profile：

- `feedInline`：首页和频道的内嵌视频；
- `immersiveWorkBrowser`：`workBrowser` 内容详情与视频集的沉浸播放。

它们共享同一播放会话、媒体描述符、错误语义和行为口径；不得按页面各自持有
`VideoPlayerController` 或各自演进自动播放/生命周期规则。剪辑、特效、RTC 和端侧远端
临时抽帧不在此决策范围内。

### 单一会话所有权

`VideoPlaybackSession` 是唯一播放命令入口，标识由
`surfaceId + postId + mediaAssetId + assetVersion + episodeIndex` 组成。它串行处理：

- `initialize`、`playByUser`、`pauseByUser`、`beginScrub`、`updateScrubTarget`、`endScrub`；
- 焦点、可见度、前后台、音频中断、切作品、切集和销毁；
- generation 递增与过期异步回调拒绝。

页面、WorkBrowser 控件、首页焦点协调器和时间轴只消费 `PlaybackSnapshot` 并向 session
发命令；不得直接调用 `play`、`pause`、`seekTo` 或保留已释放的 controller。原生 surface
只向 session 回报初始化、首帧、缓冲、位置、时长、结束和失败事件。`VideoPlayerWidget`
不再是控制器的跨页面出口。

`PlaybackSnapshot` 固定包含：

| 维度 | 枚举 / 数据 | 规则 |
| --- | --- | --- |
| `transport` | `initializing` / `ready` / `playing` / `paused` / `scrubbing` / `buffering` / `ended` / `failure` | 原生事件唯一驱动，页面不自行推断第二状态机 |
| `playIntent` | `manualPlay` / `manualPause` / `autoEligible` / `interrupted` / `awaitingUserGesture` | `manualPause` 永远压过焦点、前后台和自动恢复 |
| `controls` | `hidden` / `transient` / `pinned` | 仅控制辅助 chrome；两种 profile 的极简时间轴始终可见，暂停和拖动固定为 pinned |
| `pauseReason` | `user` / `focusLost` / `offscreen` / `appLifecycle` / `audioInterruption` / `episodeChange` / `failure` | 仅用于恢复判定与受限观测 |
| 时间 | native position、buffered、native duration、verified duration、scrub target | verified duration 为媒体真相；native duration 只用于 seek 边界和一致性校验 |

### profile × transport × controls 视觉矩阵

四级视觉必须由 `VideoTimelineVisualLevel` 及 `AppColors`、`AppSpacing`、`AppTypography`
语义 token 提供；视觉细轨和最小 `44dp` 触控热区必须分离，禁止页面写独立尺寸常量。

| 场景 | 轨道/圆点 | 时间文案 | 控制与位置 |
| --- | --- | --- | --- |
| `feedInline + playing` | `2dp` / 无视觉圆点 | 真实总时长常驻轨道右上方 | 被动细轨视觉底边贴视频底边；无左侧播放按钮，背景不使用黑色胶囊 |
| `immersiveWorkBrowser + playingIdle` | `2dp` / 无视觉圆点 | 真实总时长只在首次进入或切集后最多显示 `5s`，作为轨道右上方 overlay；与标题、正文或交集句实际碰撞时立即隐藏 | 轨道视觉底边紧贴底部互动工具栏上沿，左右与 caption/互动栏的 bottom-safe rail 对齐，无左侧播放按钮；时长不占独立行 |
| `paused` | `4dp` / `8dp` | 仅在同一个 entry-only `5s` 窗口尚未结束且无碰撞时显示 | 控制 pinned，轨道本体仍贴互动栏；媒体中央只显示无背景、无边框、三个角圆润的放大播放三角，非控件区域可续播 |
| `scrubbing` | `6dp` / `12dp` | 以更大等宽数字显示“目标时间 / 有效总时长” | 只变更虚拟 target；P0 只显示时间浮标，P1-A 在浮标上方按 descriptor 的 storyboard 显示预览帧 |

`durationUnknown` 禁用拖动；`buffering` 冻结最后位置并轻量提示；`ended` 停在末帧显示
replay；`failure` 保留同源封面和结构化恢复动作。轨道、文本和预览均不得压住互动栏、
safe area 或跨越 rail。caption 的标题、正文、交集说明等实际 `RenderParagraph`
字形矩形与右侧总时长 `RenderBox` 在同一全局坐标系做碰撞判定；不得用整条 rail
包围盒、“是否有文案”或字符数等启发式替代。隐藏视觉时长后，时间轴的
current/total 无障碍语义仍须完整。

P0 只承诺 progressive MP4/Range 的安全拖动；storyboard 是可独立关闭的 P1-A，ABR
HLS/CMAF 是可独立关闭的 P1-B。两项增强失败时都只能降级自身，不得改变 P0 播放、暂停、
拖动、恢复或错误语义。

### 手势、声音和生命周期

- feed 的媒体区 tap 是暂停/续播；标题、作者和卡片非媒体区才进入 `workBrowser`。时间轴、
  互动、视频集横滑和作品纵滑是互斥 hit region；超过 touch-slop 后取消 tap，单次意图只记录一次。
- 拖动期间不得连续 seek；释放时只提交一次 seek，取消回到拖动前位置。进入拖动前正在播放，
  仅在 seek settle 成功且仍前台可见时恢复；原本暂停始终保持暂停。
- WorkBrowser 的 active video binding 必须把 `viewportEpoch + postId + media delivery identity
  + episodeIndex + session` 原子绑定；评论分屏、筛选或异步投影重建先失效旧 binding，再按
  delivery identity 恢复当前集。评论开关、过滤临时移除/恢复、普通重建和列表重排不得重启
  总时长窗口；只有作品首次进入或真实切到另一集（包括切回既有集）才开启新的最多 `5s`
  窗口。
- Android/iOS 默认开声播放，申请短暂音频焦点；失焦、来电、离屏、后台和切集立即暂停。
  短暂中断只有 session 仍可见、仍获焦点且不是 `manualPause` 时恢复。
- Web 被浏览器拒绝的有声自动播放进入 `awaitingUserGesture`，不是 RuntimeFailure。平台能力
  必须经 `PlatformCapabilities` / platform port 暴露；业务层不得使用 `Platform.is*` 或
  `kIsWeb`。
- Android 兼容不按品牌或具体机型维护条件分支。平台层以最低支持 API、内存等级、decoder
  capability 与运行时失败证据选择广覆盖安全默认值和结构化降级，并以早期/低端物理机矩阵
  证明，而不是为单一厂商建立长期旁路。

### 可访问性与性能边界

播放/暂停、重播、静音和时间轴必须具有 button/slider role、当前/总时长 value、操作 hint、
固定步长键盘 seek 与可见焦点。TalkBack/VoiceOver 状态播报、动态字体、Reduce Motion、
横竖屏与 Web 键盘属于同一 UAT。position 更新只能重建局部 controls，不能重建整个 feed
或 `WorksImmersiveViewer`。

### 推荐行为与 QoE 分轨

内容行为仅发送满足服务端 policy 的、每会话每内容一次的 `effective_play`；它只包含推荐
归因与经校验的真实有效播放时长/比例。seek、后台、离屏、buffering 和 wall-clock dwell
不得充当有效观看。原始 TTFF、ready、rebuffer、seek、时长偏差和设备/网络维度只进入 Ops
强类型 QoE 事件，禁止进入推荐热路径或以 `AnalyticsEvent.properties` 偷渡。

具体 VOD 资产、storyboard、处理状态和 QoE 存储/告警合同由
`runtime/runtime-media` 统一定义；本 L2 只规定展示、会话和用户旅程边界。
