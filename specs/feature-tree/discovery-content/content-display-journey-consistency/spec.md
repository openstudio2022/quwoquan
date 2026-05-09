# L2 特性：content-display-journey-consistency

## 背景与动机

当前内容展示旅程存在三类结构性断裂：

1. 不同 feed 来源的 handoff 规则不一致。发现页可以把部分状态带入媒体浏览器，但圈子流进入浏览器时仍存在文案、关注态、点赞态和返回回写不完整的问题。
2. 作者主页已冻结 `RelationshipCapabilityView` 五态关系矩阵，但 feed / viewer 仍混用二元 `isFollowing` 与局部状态，导致作者主页按钮矩阵与浏览器中的作者关系态可能漂移。
3. 现有异步写回以“点击即发请求”为主，无法同时兼顾实时交互、反复点击合并、失败重试与系统级统一配置。

本 L2 的目标是把“内容来源 -> 沉浸浏览 -> 作者主页 -> 返回原来源”的端到端旅程冻结为单一规格基线，确保发现页与圈子流两类来源都满足同源数据、同源状态、同源标识与同源回写。

## 目标用户

- 在发现页浏览图片、视频、微趣媒体并进入沉浸式浏览器的用户。
- 在发现页文章频道或圈子频道浏览文章，并进入沉浸式文章阅读器的用户。
- 在圈子流中浏览 post 并进入沉浸式浏览器的用户。
- 从沉浸式浏览器点击作者头像进入作者主页，并期望返回后状态无漂移的用户。
- 在弱网、反复点击与重入场景下仍要求界面即时反馈且状态最终一致的用户。

## 功能范围

### F1：多来源统一 handoff

- 正式覆盖 `discovery feed` 与 `circle feed` 两类来源。
- 两类来源进入媒体浏览器或文章阅读器时都必须传入：
  - canonical post 标识
  - canonical author 标识
  - post 文案与媒体资源
  - 当前 post 互动状态
  - 当前 author 关系态
  - 返回来源所需上下文

### F2：对象级唯一真相源

- `user` 负责作者资料、关系能力与关注状态。
- `post` 负责媒体、标题、正文、赞评转藏计数与 post 互动状态。
- `circle` 只负责 feed 来源上下文，不拥有作者关系态或 post 互动真相。

### F3：统一标识符语义

- 对外路由继续保留 `/user/{usernameSlug}`。
- 内部用户 canonical key 统一为 `ProfileSubjectId`。
- post 作者引用统一为 `authorProfileSubjectId`。
- 所有互动状态与 viewer 回写一律使用 `PostId` 作为 post canonical key。

### F4：Provider 自动同步

- feed、viewer、profile 共用统一 provider 同步关系态与互动状态。
- `profile` 按 `RelationshipCapabilityView` 渲染按钮矩阵，不再回退到多套本地布尔状态拼装。
- `viewer` 和 feed 不再通过 callback 链临时传布尔值保持一致。

### F5：延迟批同步与失败重试

- 用户点击后 UI 立即乐观更新。
- 云端持久化不立刻发送，而是进入本地 `sync outbox`。
- 默认 `10s` 后聚合同步一次；窗口内多次操作按 `latest_wins` 合并。
- 默认 `5min` 后重试失败批次；如果等待窗口内又产生新操作，立即合并并触发下一轮批同步。
- 上述参数归 `sys.client_state_sync.*`，本地有默认值，云端可下发覆盖并本地持久化。

### F6：文案与展示一致性

- 图片、视频、微趣、文章进入浏览器/阅读器后，标题（可选）和正文（可选）必须与对应 post 展示一致。
- viewer 中作者头像、昵称、圈子来源、关注态、点赞态、计数展示与 feed / profile 一致。

## Out of Scope

- RTC 语音/视频能力本身的产品化重做。
- 圈子 feed 排序、推荐与召回策略。
- profile 壳层、背景拉伸、Tab 吸顶等已有 story 的视觉重构。
- 新增独立聚合后端或新路由形态。

## 约束

- 主归属沿用 `discovery-content/content-display-journey-consistency`，不新建平行 L2。
- 所有字段、路由、operation、request context 均遵守 metadata-first：
  - `service.yaml`：operation / path / method
  - `app_routes.yaml`：route 真相源
  - projections：DTO 真相源
- 所有 Repository 必须支持 `appDataSourceModeProvider` 的 Mock/Remote 切换。
- 运行时同步参数属于 `sys.*`，不得落到 `ops.*`、业务 feature flag 或 `ui_config.yaml`。
- 不允许再以 `username / userId / authorId / subAccountId` 混合作为状态 key。

## 对标输入与吸收结论

### 外部对标

| 对标 | 借鉴点 | 不借鉴点 |
|------|--------|----------|
| 小红书 | 媒体浏览器进入作者主页后，返回状态应无闪烁收敛 | 不照搬其 feed / 关系对象建模 |
| 抖音 | 媒体浏览与作者页之间的连续状态感、强即时反馈 | 不照搬视频单轨信息架构 |
| 微博 | 社区流来源进入详情页后互动状态一致 | 不照搬弱关系社交模型 |

### 吸收结论

- 必须冻结“跨来源一致性”而不是只冻结 viewer UI。
- 必须把“关系态”与“post 互动态”拆开建模。
- 必须把实时 UI 与延迟批同步分层，而不是把“点击是否立即发请求”当成纯实现细节。

## 角色分工

- 产品：冻结来源范围、对象边界、交互不可打折基线、灰度与回滚条件。
- 架构：冻结 canonical key、Provider 边界、outbox 同步模型、`sys.*` 配置分层。
- 客户端：落地 viewer / feed / profile 的 provider 同步、outbox、回写与重试。
- 云端：保证 `SubAccountProfileView`、`RelationshipCapabilityView`、post projections 与 `sys.*` 配置下发契约一致。
- 测试：建立 T1~T4 覆盖，重点验证 discovery / circle / viewer / profile 四方闭环。

## 既有 Story 覆盖矩阵

| 既有节点 | 当前职责 | 本次如何处理 |
|----------|----------|--------------|
| `feed-item-dto-contract` | DTO 类型化与 projections 一致性 | 继续作为前置依赖，不重复定义 DTO 真相源 |
| `content-action-intent-contract` | like/save/follow 乐观更新基础 | 扩展为 provider + outbox + 批同步策略的依赖基线 |
| `photo-display-journey` / `video-display-journey` / `moment-display-journey` / `article-display-journey` | 各内容类型的来源-浏览器/阅读器-作者页旅程 | 继续保留，消费本次新增的 handoff / sync contract |
| `dual-rail-discovery-redesign/works-immersive-viewer` | 作品轨沉浸浏览交互壳层 | 继续负责表现层，不负责多来源状态真相源 |
| `owner-subaccount-homepage-unification` | profile 按钮矩阵与 `RelationshipCapabilityView` 真相源 | 作为被依赖节点，不作为本次主归属 |

## 数据生命周期合同

### 用户关系态

- 用户点击关注/取消关注后，`UserRelationshipStateProvider` 立即更新内存态。
- 同步意图写入本地 `sync outbox`，按 `ProfileSubjectId` 聚合最终状态。
- 达到 `flush_delay_sec` 后批量同步到云端。
- 失败后保留 pending intent，达到 `retry_delay_sec` 后重试。
- pending intent 超过 `max_pending_age_sec` 仍未成功时进入人工/诊断可观测路径，但本地 UI 仍以最后用户意图为准，等待 reconcile。

### Post 互动状态

- like/save/share 等写入 `PostInteractionStateProvider`，立即反馈到 feed / viewer / profile 交叉展示区域。
- 同步意图按 `PostId` 聚合，只保留最终意图。
- 批同步成功后更新本地已确认状态；若失败则保留 outbox，等待下一轮 flush。

## 小趣 / 权限 / 分享边界

- 本次不涉及助手链路，不允许通过 assistant runtime 做垂类特判。
- `self / not_following / following / followed_by / mutual / blocked / blocked_by` 的动作权限一律由 `RelationshipCapabilityView` 决定。
- 分享能力不扩 scope；本次仅要求 share 计数与状态回写一致，不新增分享生命周期合同。

## 非功能目标

### SLO / KPI

- UI 乐观反馈：点击后 `p95 < 100ms` 可见状态变化。
- 默认首次 flush：最后一次同类操作后 `10s` 内触发批同步。
- 默认失败重试：`5min` 内触发下一轮批同步，参数由 `sys.client_state_sync.*` 可配置。
- 正常网络下，从点击到云端持久化成功的 `p95 < 30s`。
- viewer / profile / feed 的状态漂移率在灰度阶段必须可观测，并以 `reconcile_mismatch_rate` 作为 guardrail。

### 弱网 / 容量 / 性能

- 弱网下不得丢失 pending intent。
- 同一对象反复点击必须按 `latest_wins` 合并，不产生无限增殖的重试请求。
- 单设备本地 outbox 至少支持 1000 条 pending intents 与 72h 保留。
- 前台恢复、网络恢复时允许触发一次立即 flush，但不得绕过 `sys.*` 风险配置。

## 迁移、灰度与回滚要求

- 迁移顺序固定：
  1. 扩 journey 基线
  2. 新增 `circle-feed-viewer-handoff-contract`
  3. 新增 `viewer-profile-state-sync-contract`
  4. 各内容类型旅程消费新 contract
- 灰度通过 `ops.*` feature flag 控制能力开关，通过 `sys.client_state_sync.*` 控制运行时参数。
- 建议灰度路径：`5% -> 25% -> 50% -> 100%`。
- 关键观测：
  - outbox pending 数
  - flush 成功率
  - retry 成功率
  - reconcile mismatch rate
  - viewer/profile action-matrix mismatch
- 回滚条件：
  - canonical key 解析错误
  - 关系态与按钮矩阵不一致
  - outbox flush 持续失败
  - 状态漂移超过 guardrail

## 验收重点

1. discovery 与 circle 两类 feed 来源进入 viewer 的 handoff 契约已冻结并可被复用。
2. `user` 与 `post` 的对象级真相源已冻结，且 provider 边界清晰。
3. `ProfileSubjectId` / `authorProfileSubjectId` / `PostId` 的 canonical key 语义已冻结，不再混用。
4. `Provider` 自动同步 + outbox 延迟批同步 + 失败重试 + `sys.*` 配置下发已冻结为正式基线。
5. 进入 `/design` 后不需要再次裁决“是否立即发请求”“是否以 username 做 key”“圈子流是否纳入范围”等前置问题。
