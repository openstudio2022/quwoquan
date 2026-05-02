# L3 Scenario: follow-relationship

## 节点定位

- `L1_capability`: `user-identity-profile-relationship`
- `L2_journey`: `persona-follow-graph`
- `L3_scenario`: `follow-relationship`

本场景冻结分身关系写入侧的业务边界。它对应的是 user 域独立业务对象 `FollowEdge` 的 command side，而不是 `UserProfile` 聚合本身。分身关系的建立、取消与幂等由 `FollowEdge` 负责；粉丝/关注列表读取和分页由 `social-graph-read` 负责。

## 背景与动机

当前分身能力里，“谁关注了谁”已经不只是一个布尔关系，而是作者身份、主页按钮矩阵、通知和推荐信号的共同起点。但目前缺少一版按业务对象拆清楚的写侧规格：

1. Follow 行为与 `UserProfile` 统计、`BlockEdge` 门禁、通知/推荐事件彼此关联，但边界没有冻结。
2. 关注动作的真正主体应是分身 `profileSubjectId / subAccountId`，而不是 owner 或匿名的 `userId`。
3. 旧节点 `follow-unfollow-contract` 仍是 current 占位，没有形成可直接进入 `/design` 的 Scenario。

## 业务对象划分

### `FollowEdge`

- 领域：`user`
- 业务对象：独立实体，不是聚合根
- 元数据目录：`contracts/metadata/user/follow_edge/`
- 主职责：维护 `follower -> followee` 单向关系边
- 存储：MongoDB
- 原因：高并发写入与社交图谱扩展优先，适合独立水平扩展

### `UserProfile`

- 领域：`user`
- 业务对象：聚合根
- 元数据目录：`contracts/metadata/user/user_profile/`
- 主职责：维护 `followerCount / followingCount` 等冗余统计、公开身份、owner/persona 聚合关系
- 存储：PostgreSQL + Redis
- 与本场景关系：不直接拥有 follow 写入，而是通过 `UserFollowed / UserUnfollowed` 事件更新计数

### `BlockEdge`

- 领域：`user`
- 业务对象：独立实体
- 元数据目录：`contracts/metadata/user/block_edge/`
- 存储：PostgreSQL + Redis
- 与本场景关系：作为 follow 写入门禁与 read projection 的过滤因子

## 功能范围

### F1. follow / unfollow 的动作主体

- follow / unfollow 的命令主体必须是当前 active persona 或显式选择的 persona。
- owner 不能作为默认 follow 主体参与社交关系建立。
- follow 边的 `followerId / followeeId` 语义必须统一映射到 `ProfileSubject` 级别，而不是漂移在 owner/user 级别。

### F2. 幂等与唯一约束

- 同一 `followerId + followeeId` 只允许存在 1 条有效关注边。
- 重复 follow 必须幂等，不得重复计数。
- unfollow 不存在的边应当是安全 no-op 或明确可恢复错误，不允许破坏计数。

### F3. Block 门禁

- 如果 `BlockEdge` 表示任一方向的强屏蔽，follow 写入必须被拒绝或无效化，具体语义由 user 域统一定义。
- follow 写入侧不能绕过 `BlockEdge` 直接落边。
- follow 写入成功与否，不得泄露不应暴露的屏蔽细节。

### F4. 计数与事件副作用

- `FollowEdge` 写入成功后，发布 `UserFollowed / UserUnfollowed` 事件。
- `UserProfile` 侧通过事件更新 `followerCount / followingCount`。
- 计数修正属于跨业务对象副作用，不回写到 `FollowEdge` 主对象。

### F5. 来源与审计

- 写入可携带 `source`，用于区分 `profile / recommendation / circle` 等来源。
- `source` 只用于审计和策略优化，不改变 follow 边主语义。
- 平台审计可追踪 follow 命令与分身主体；普通读接口不得反推出 owner 映射。

## 领域边界

### 本场景负责

- `FollowEdge` 的 follow / unfollow 命令语义
- 幂等、唯一约束与 block 门禁
- 事件发布与跨对象计数同步边界

### 本场景不负责

- 粉丝/关注列表分页读取：归 `social-graph-read`
- 主页按钮矩阵 UI：消费关系能力投影，不在本场景定义
- 分身管理与公开身份：归 `persona-management` 和 `persona-profile-subject-and-visibility`

## 元数据与接口真相源

- `FollowUser / UnfollowUser` 的 path、operation、request_context 真相源归 `contracts/metadata/user/follow_edge/service.yaml` 与 `_shared/request_context.yaml`
- `FollowEdge` 字段、唯一约束、事件与存储真相源分别归：
  - `user/follow_edge/fields.yaml`
  - `user/follow_edge/events.yaml`
  - `user/follow_edge/storage.yaml`
- user 域之外不得复制 follow 写入契约

## 权限边界与数据生命周期

- 只有当前登录 owner 持有的 active persona 才能发起 follow / unfollow。
- `FollowEdge` 删除不等于记录通知或推荐信号被立即抹除；推荐与通知系统自行消费事件进行修正。
- follow 关系删除后，`UserProfile` 统计必须最终一致修正。

## 不做什么（Out of Scope）

- 粉丝/关注列表分页 UI。
- 主页按钮矩阵渲染。
- 推荐算法如何使用社交图谱。
- 圈子或评论里的显式身份选择 UI。

## 对标输入

| 对标 | 吸收点 |
|---|---|
| 微博 | 公开 follow 关系与粉丝传播链 |
| 小红书 | 主页 follow 按钮与创作者关系建立 |
| 微信 | 强关系产品里的门禁和幂等要求 |

## 非功能目标

- follow / unfollow 命令 P95 < 500ms。
- 幂等重试不导致重复边或重复计数。
- 关注关系写入在弱网重试下不发生身份串号。

## 验收重点

1. `FollowEdge` 被明确冻结为 user 域独立业务对象，follow 写入不再挂在 `UserProfile` 聚合内部实现。
2. follow / unfollow 的主体是分身级 `ProfileSubject`，不是 owner。
3. block 门禁、幂等与统计副作用边界清晰，可直接进入 `/design`。
