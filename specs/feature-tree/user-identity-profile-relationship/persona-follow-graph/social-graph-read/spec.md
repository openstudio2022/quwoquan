# L3 Scenario: social-graph-read

## 节点定位

- `L1_capability`: `user-identity-profile-relationship`
- `L2_journey`: `persona-follow-graph`
- `L3_scenario`: `social-graph-read`

本场景冻结分身社交图谱的 read side：粉丝/关注分页、关系查询与关系能力投影。它消费 `FollowEdge`、`BlockEdge` 与 `ProfileSubject`，为主页按钮矩阵、关注页、聊天门禁和推荐读取提供统一读模型。

## 背景与动机

当前图谱读取有三个问题：

1. follow 写侧与 read 侧没有在特性树上拆开，导致分页读取、能力投影和按钮矩阵混在一起。
2. `GetRelationshipCapability` 已在 metadata 中存在，但还没有在 PRD 里明确它是哪个业务对象组合出来的读模型。
3. 粉丝/关注列表需要同时满足分身隔离、Block 过滤、公开身份展示和分页稳定性，现有占位 Story 无法支撑 `/design`。

## 业务对象与数据划分

### `FollowEdge`

- 领域：`user`
- 存储：MongoDB
- 作用：提供社交图谱边与分页读取主数据源

### `BlockEdge`

- 领域：`user`
- 存储：PostgreSQL + Redis
- 作用：在图谱读取、关系能力和消息门禁中提供过滤条件

### `ProfileSubject`

- 领域：`user`
- 存储来源：`UserProfile + Persona` 合成读模型
- 作用：为列表与关系能力提供稳定展示字段，不暴露 owner 映射

本场景不拥有这些业务对象的写入，只消费其 read model / projection。

## 功能范围

### F1. 粉丝/关注分页读取

第一版冻结以下读路径：

- `ListFollowing`
- `ListFollowers`

要求：

- 分页主键与排序必须围绕 `FollowEdge.createdAt` 或等价稳定游标。
- 列表项展示使用 `ProfileSubject` 公共字段，不直接透出 owner 管理信息。
- 公开读取必须遵守分身可见性与 block 过滤规则。

### F2. 基础关系查询

第一版保留：

- `GetRelationship`

它用于回答“是否关注 / 是否互关”等基础关系态，不承担复杂按钮矩阵所有细节。

### F3. 关系能力投影

第一版冻结：

- `GetRelationshipCapability`

它是 read projection，不是新的写对象。投影来源：

- `FollowEdge`
- `BlockEdge`
- `ProfileSubject`

投影至少稳定提供：

- `relationState`
- `canFollow`
- `canUnfollow`
- `canMessage`
- `canFollowBack`
- `canStartVoiceCall`
- `canStartVideoCall`
- `isBlocked`
- `isBlockedBy`

### F4. Block 与可见性过滤

- 被 block 或 strict isolation 的主体，在列表与能力读取中必须使用一致的不可见或受限语义。
- 列表分页不能因为过滤而串页或重复页。
- 关系能力读取不得泄露超出产品允许范围的 block 事实。

### F5. 主页与聊天消费边界

- 主页按钮矩阵直接消费 `RelationshipCapabilityView`，不再手写布尔组合。
- 聊天/RTC 门禁只消费能力位，不自行推断 follow/block 组合。
- follower/following 页只消费分页 read model，不直接读取 FollowEdge 原始对象。

## 领域边界

### 本场景负责

- Follow 图谱列表读取与分页稳定性
- `GetRelationship` 与 `GetRelationshipCapability` 读投影
- Block 与可见性过滤后的公开读语义

### 本场景不负责

- follow / unfollow 命令写入：归 `follow-relationship`
- 分身管理与资料继承：归 `persona-management`、`persona-profile-subject-and-visibility`
- 主页壳层视觉实现：归 `profile-homepage-redesign`

## 元数据与接口真相源

- 图谱读取和能力读取的 operation/path/request_context 真相源归：
  - `contracts/metadata/user/follow_edge/service.yaml`
  - `_shared/request_context.yaml`
- `RelationshipCapabilityView` 真相源归 `contracts/metadata/user/follow_edge/fields.yaml`
- `ProfileSubject` 公开身份字段真相源归 `contracts/metadata/user/user_profile/*`
- `BlockEdge` 的过滤语义真相源归 `contracts/metadata/user/block_edge/*`

## 权限边界与数据生命周期

- 普通读接口只能读取经过 `ProfileSubject` 和可见性过滤后的列表项。
- 内部可以基于 owner 审计映射做治理，但对外列表不得暴露 owner 关联。
- 分身停用后，其记录 follow 图谱如何继续公开展示，必须服从 `persona-profile-subject-and-visibility` 的公开可见性合同。

## 不做什么（Out of Scope）

- follow / unfollow 写入命令。
- 推荐引擎如何消费图谱排序。
- 主页按钮组件实现本身。
- group/circle 成员图谱。

## 对标输入

| 对标 | 吸收点 |
|---|---|
| 微博 | 粉丝/关注公开读取与互关态展示 |
| 小红书 | 主页关系按钮矩阵与 follow list 展示 |
| 微信 | block/关系门禁的一致性要求 |

## 非功能目标

- follower / following 首屏分页读取 P95 < 800ms。
- `GetRelationshipCapability` P95 < 300ms。
- 过滤场景下分页不重复、不漏页、不串页。

## 验收重点

1. `social-graph-read` 成为 Follow 图谱 read side 的唯一 Scenario，不再与写入侧混杂。
2. `RelationshipCapabilityView` 的来源、用途与消费边界冻结。
3. 列表分页、Block 过滤、可见性过滤和公开身份展示可以直接进入 `/design`。
