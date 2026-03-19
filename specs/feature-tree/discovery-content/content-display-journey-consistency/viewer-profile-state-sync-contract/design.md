# viewer-profile-state-sync-contract 设计方案

## 设计动因

viewer 与 author profile 当前存在三类结构性问题：

1. profile 已有 `RelationshipCapabilityView`，但 `profile_state_provider.dart` 仍以局部 `isFollowing` 作为操作主状态。
2. viewer / feed / profile 之间同时存在 `userId`、`authorId`、`usernameSlug` 等不同 key，导致同一用户可能被写入多套状态集合。
3. 点击 follow / like / save 仍偏向“单次点击单次请求”，无法承接反复点击合并、失败重试和运行时参数下发。

本 Scenario 的目标是冻结 viewer 与 profile 之间的 canonical key、共享 provider、outbox 聚合同步与返回收敛模型。

## 上游输入评审

| 输入 | 结论 |
|------|------|
| `viewer-profile-state-sync-contract/spec.md` | 范围与验收已明确，可直接进入细化设计 |
| `content-display-journey-consistency/design.md` | 已选定“shared provider 为主、handoff/result 为补强、outbox 负责延迟批同步”的 Journey 方案 |
| `owner-subaccount-homepage-unification/design.md` | `ProfileSubjectView` 与 `RelationshipCapabilityView` 已可直接复用 |
| `content-action-intent-contract/design.md` | 可复用乐观更新与失败回滚边界，但要扩展到 outbox 聚合同步 |
| 现状代码 | `profile_state_provider.dart` 仍以局部 `isFollowing` 触发远端写入；`UserProfileRouteExtra` 仍偏展示型，不承载 canonical key |

## 对标输入分析

| 对标 | 吸收点 | 不吸收点 |
|------|--------|----------|
| 小红书 | 作者页返回 viewer 后关系态立即收敛 | 不照搬其数据模型 |
| 抖音 | 点击动作即时反馈、返回无明显闪烁 | 不照搬其视频壳层 |

内部对标：

- `ContentRuntimeConfigState.fromAppConfig()` 已经具备“本地默认 + 远端覆盖”的解析模式，可直接扩展到 sync 参数。

## 方案对比

### 方案 A：保留页面内局部状态，返回时手动同步

优点：

- 改动小。

缺点：

- 不能解决多实例与重入问题。
- `RelationshipCapabilityView` 仍无法成为唯一真相源。

### 方案 B：共享 provider + 立即远端写入

优点：

- 页面状态统一。

缺点：

- 仍会产生频繁请求，无法承接 10s 批同步与 5min 重试要求。

### 方案 C：共享 provider + outbox 延迟批同步

优点：

- 同时满足统一真相源、即时 UI 与延迟批同步。
- 能以 `sys.client_state_sync.*` 做系统级管控。

缺点：

- 需要新增 scheduler / outbox / reconcile 机制。

## 选型决策

选定方案：**方案 C**

原因：

1. 它是唯一能同时满足 A1/A2/A3 的方案。
2. 它把 `RelationshipCapabilityView` 真正提升为关系态主来源。
3. 它对弱网与高频点击更稳健。

## 关键设计决策

### KD1：用户与 post 状态分离建模

- 用户关系态：
  - key: `ProfileSubjectId`
  - source: `RelationshipCapabilityView`
  - provider: `UserRelationshipStateProvider`
- post 互动态：
  - key: `PostId`
  - source: content projection + local pending intents
  - provider: `PostInteractionStateProvider`

### KD2：canonical key 兼容路径

- 外部路由仍使用 `/user/{username}`。
- `UserProfileRouteExtra` 新增 canonical 用户 key 字段，展示字段仍可保留。
- viewer 与 profile 的 follow 状态不再用 `usernameSlug`、`authorId`、`userId` 作为内部 key。

### KD3：profile 关系态消费规则

- `profile_state_provider.dart` 不再以 `_state.isFollowing` 作为按钮矩阵主来源。
- `ProfileActionBar` 始终优先消费 `RelationshipCapabilityView`。
- `toggleFollow()` 先更新共享 provider，再进入 outbox；局部 `isFollowing` 只作为兼容期镜像，最终可移除。

### KD4：outbox 结构

建议本地结构：

- `ClientStateSyncIntent`
  - `objectType`
  - `objectId`
  - `intentType`
  - `desiredState`
  - `createdAt`
- `ClientStateSyncOutboxEntry`
  - `coalesceKey`
  - `latestIntent`
  - `nextFlushAt`
  - `retryCount`
  - `lastErrorCode`

### KD5：flush / retry 调度

- 默认首次 flush：最后一次操作后 `10s`
- 默认 retry：失败后 `5min`
- 合并：`latest_wins`
- 恢复触发：
  - app foreground resume
  - network recovered

### KD6：reconcile 规则

- 当 follow / like / save 远端成功后，标记本地 intent 已确认。
- 当远端失败但用户又产生新意图时，以新意图覆盖旧 pending。
- 当 profile reload 获得新的 `RelationshipCapabilityView` 时，以 capability 作为关系态最终收敛依据。

## metadata / codegen 方案

需要修改或确认的 metadata：

- `quwoquan_service/contracts/metadata/content/post/fields.yaml`
  - 新增 `authorProfileSubjectId`
- `quwoquan_service/contracts/metadata/content/post/service.yaml`
  - `GetAppConfig` 扩展 `client_state_sync`
- `quwoquan_service/contracts/metadata/_control_plane/platform/config_schema.yaml`
  - 新增 `sys.client_state_sync.*`
- `quwoquan_service/contracts/metadata/user/follow_edge/service.yaml`
  - 保持 `GetRelationshipCapability` 为正式响应真相源

codegen 预期影响：

- content DTO 生成物新增 canonical 作者 key
- content API metadata / request page id 保持稳定
- control plane 生成物新增 client sync 配置 schema

## 字段演进、迁移 / 回填、双读双写

### 字段演进

- `authorId` -> `authorProfileSubjectId`
- `isFollowing` 局部主状态 -> provider 派生状态

### 迁移 / 回填

- App 在兼容期优先读取 `authorProfileSubjectId`，缺失时 fallback `authorId`
- 现有页面级 Set/Map 数据在首次 provider 化时迁移到 provider state

### 双读 / 双写

- 双读：canonical key 优先，legacy key fallback
- 双写：不做长期双写；只保留局部镜像到完全迁移完成为止

## feature flag、观测、SLO 验证与回滚

### feature flag

- `ops.content.viewer_profile_state_sync_v1`
- `ops.content.client_state_sync_outbox_v1`

### 观测

- `viewer_profile_follow_mismatch_total`
- `client_state_sync_outbox_pending_count`
- `client_state_sync_coalesce_count`
- `client_state_sync_retry_total`
- `relationship_capability_fallback_hit_total`

### SLO

- 点击后 UI 变化 `p95 < 100ms`
- flush 触发 `<= 10s`
- retry 触发 `<= 5min`

### 回滚

1. 关闭 `viewer_profile_state_sync_v1`
2. 关闭 `client_state_sync_outbox_v1`
3. 保留 `RelationshipCapabilityView` 读路径与 legacy key fallback

## TDD / ATDD 策略

| 验收 | 测试层 | 策略 |
|------|--------|------|
| A1 | T1, T2, T3 | canonical key schema、provider key mapping、integration consistency |
| A2 | T2, T3, T4 | viewer/profile/feed shared provider 集成与重入回归 |
| A3 | T1, T2, T3, T4 | config schema、coalesce/retry、弱网恢复、远端覆盖配置 |
| S1 | T3, T4 | 灰度与回滚演练 |

## plan slice 与 T1~T4 证据矩阵映射

| Slice | 目标 | 主要验收 | 主要证据 |
|-------|------|----------|----------|
| P1 | 冻结 canonical key 与 sync config metadata | A1, A3 | T1 |
| P2 | 接入 codegen 并收口 provider 边界 | A1, A2 | T1, T2, T3 |
| P3 | 落地 outbox / scheduler / reconcile | A3 | T2, T3, T4 |
| P4 | 完成灰度、观测与回滚验证 | S1 | T3, T4 |

## 未来演进

- 将 share/comment 等更完整的交互也接入同一 outbox。
- 在 provider 稳定后移除 `ProfileState.isFollowing`。
- 将 `UserProfileRouteExtra` 从展示型 extra 进一步收敛为 canonical route context。
