# L3 特性：viewer-profile-state-sync-contract

## 背景与动机

当前沉浸式媒体浏览器与作者主页之间存在三类不一致：

1. viewer 使用局部 `isFollowing` / `likedPosts` 等状态，而 profile 使用 `RelationshipCapabilityView`，导致作者关系态与按钮矩阵可能漂移。
2. viewer、profile、feed 混用 `username / userId / authorId` 等标识，缺少统一 canonical key。
3. 异步写回以“单次点击单次请求”为主，弱网、反复点击与返回重入场景下难以保证性能与最终一致性。

本 scenario 的目标是冻结 viewer 与 profile 之间的对象级真相源、canonical key、Provider 自动同步与 outbox 批同步策略。

## 目标用户

- 在 viewer 中点击作者头像进入作者主页，并期望返回后关系态立即一致的用户。
- 在作者主页执行关注/取消关注后，希望 viewer 与原 feed 不闪烁同步的用户。
- 在弱网或频繁点击场景下，仍要求状态最终一致且不重复触发网络写放大的用户。

## 功能范围

### F1：canonical key 统一

- 外部路由保留 `/user/{usernameSlug}`。
- 内部用户状态 canonical key 冻结为 `ProfileSubjectId`。
- post 作者引用字段冻结为 `authorProfileSubjectId`。
- viewer / profile / provider 不再使用 `usernameSlug` 作为内部状态 key。

### F2：对象级真相源统一

- 用户资料与关系态：
  - `SubAccountProfileView`
  - `RelationshipCapabilityView`
  - `UserRelationshipStateProvider`
- post 互动态：
  - `PostInteractionStateProvider`
  - `PostId`
- profile 按钮矩阵仅消费 `RelationshipCapabilityView`。

### F3：Provider 自动同步

- viewer、profile、feed 同时 watch 统一 provider。
- 关注/取消关注不再依赖 callback 手动回传布尔值。
- profile 内关系态变化后，viewer 与 feed 自动收敛到同一状态。

### F4：延迟批同步与失败重试

- 点击后 UI 立即乐观更新 provider。
- 关系态与 post 互动态写入本地 `sync outbox`。
- 默认 `10s` 聚合窗口批同步，窗口内对同一对象采用 `latest_wins`。
- 默认 `5min` 重试失败批次。
- `sys.client_state_sync.*` 为运行时参数唯一真相源，本地默认、云端可下发并持久化。

## Out of Scope

- author profile 头图、Tab、壳层交互重做。
- 新增独立 BFF 或路由形态。
- RTC 能力与消息能力本身的产品化变更。
- article 详情页与非 viewer 页面同步策略重做。

## 约束

- 必须消费 `owner-subaccount-homepage-unification` 已冻结的 `RelationshipCapabilityView` 关系矩阵。
- 不允许 `capability` 与本地布尔状态长期双写。
- 不允许把运行时 flush / retry 参数落到 `ui_config.yaml` 或业务 feature flag。
- 不允许使用 `usernameSlug` 作为内部关系态 map key。

## 对标输入与吸收结论

| 对标 | 借鉴点 | 不借鉴点 |
|------|--------|----------|
| 小红书 | 作者页返回 viewer 后关注态收敛无闪烁 | 不照搬其社交对象层次 |
| 抖音 | 沉浸浏览与作者页切换的连续反馈 | 不照搬视频单轨结构 |

吸收结论：

- 关系态必须用对象真相源驱动，而不是页面局部状态拼装。
- 同步主链路应以共享 provider 为主，route result 只做补强。
- 网络写回必须与 UI 即时反馈分层。

## 角色分工

- 产品：冻结 canonical key、状态源、同步与重试行为。
- 架构：冻结 provider 边界、outbox、`sys.client_state_sync.*` 配置分层。
- 客户端：落地 provider、outbox、聚合同步、失败重试与 reconcile。
- 云端：提供 `RelationshipCapabilityView` 与 `sys.*` 配置下发能力。
- 测试：覆盖弱网、重入、反复点击与返回同步。

## 既有 Story 覆盖矩阵

| 既有节点 | 当前职责 | 本 scenario 处理方式 |
|----------|----------|----------------------|
| `owner-subaccount-homepage-unification` | 关系态按钮矩阵、ProfileSubject 语义 | 直接依赖，不重新定义关系矩阵 |
| `content-action-intent-contract` | 乐观更新基础 | 扩展到 provider + outbox + 批同步 |
| `photo/video/moment-display-journey` | 各媒体类型旅程 | 依赖本 contract 消费统一状态源与同步协议 |

## 数据生命周期合同

- `FollowIntent`
  - 创建：用户点击 follow/unfollow
  - 本地态：立即写入 `UserRelationshipStateProvider`
  - 持久化：写入 outbox
  - flush：默认 10s
  - retry：默认 5min
  - reconcile：以云端最终 capability 为准
- `PostInteractionIntent`
  - 创建：用户点击 like/save/share
  - 本地态：立即写入 `PostInteractionStateProvider`
  - 持久化：写入 outbox
  - 聚合：同一 `PostId` 采用 `latest_wins`

## 小趣 / 权限 / 分享边界

- 不涉及助手链路与小趣 runtime 特判。
- `blocked / blocked_by / self / mutual` 等权限态一律由 `RelationshipCapabilityView` 决定。
- share 仅要求状态同步与计数一致，不扩展分享生命周期合同。

## 非功能目标

- UI 状态更新：点击后 `p95 < 100ms`
- 正常网络下状态持久化收敛：`p95 < 30s`
- flush 默认 `10s`，retry 默认 `5min`
- 单设备 outbox 至少支持 1000 条 pending intents 与 72h 保留
- flush / retry / reconcile 均可观测、可审计、可回滚

## 迁移、灰度与回滚要求

- 灰度开关：建议使用 `ops.content.viewer_profile_state_sync_v1`
- 运行时参数：`sys.client_state_sync.*`
- 灰度顺序：`5% -> 25% -> 50% -> 100%`
- 回滚条件：
  - canonical key 解析错误
  - capability 与按钮矩阵不一致
  - outbox backlog 持续升高
  - reconcile mismatch 超阈值

## 验收重点

1. viewer / profile / feed 已共享统一 provider，不再靠 callback 布尔值保持一致。
2. canonical key 语义已冻结，`ProfileSubjectId` 成为内部用户唯一 key。
3. 延迟批同步、失败重试与 `sys.client_state_sync.*` 下发能力已冻结。
4. 进入 `/design` 后不再需要重新讨论“点击后是否立刻发请求”“username 是否可作为状态 key”。
