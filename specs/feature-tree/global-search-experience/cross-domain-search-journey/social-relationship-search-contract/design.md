# social-relationship-search-contract 设计方案

## 设计动因

“朋友”已经在 PRD 中被正式更名为“社交关系”，设计阶段必须把它从 chat 的历史联系人搜索能力中彻底抽离，否则 Search UI 和 metadata 会继续挂错域。

## 上游输入评审

| 输入 | 当前结论 |
|---|---|
| `social-relationship-search-contract/spec.md` | 已冻结社交关系命名、对象边界与 user 域真相源 |
| `social-relationship-search-contract/acceptance.yaml` | `A1/S1` 足以承接实施切片 |
| `persona-follow-graph/design.md` | `ProfileSubjectView` 与 `RelationshipCapabilityView` 已可作为公开身份和关系态真相源 |

## 对标输入分析

- 对标中可以借鉴微信联系人结果的列表心智，但不能照搬其领域归属。
- 本产品需要的是“公开身份 + 关系态”的组合读模型。

## 方案对比

### 方案 A：继续复用 `SearchContacts`，只改 UI 文案

优点：

- 服务端改动小。

缺点：

- 领域归属仍错误。
- 无法稳定表达 not_following / mutual / followed_by 等关系态。

### 方案 B：只做 `SearchUsers`，关系态由 App 二次拼装

优点：

- 搜索实现简单。

缺点：

- App 继续承担第二套关系推导。
- 与 `RelationshipCapabilityView` 真相源冲突。

### 方案 C：在 `user` 域新增 `SearchSocialRelations`，返回公开身份 + 关系态

优点：

- 产品命名、领域归属与结果模型一次性一致。
- 可直接复用 `ProfileSubjectView + RelationshipCapabilityView`。

缺点：

- 需要新增 user 域 search operation。

## 选型决策

**选定方案：方案 C**

## 关键设计决策

### KD1：搜索中的“人”统一由 `user/user_profile` 真相源承接

不再由 chat contact 决定产品定义。

### KD2：返回模型冻结为 `SocialRelationSearchItemView`

最小字段：

- `profileSubjectId`
- `username`
- `displayName`
- `avatarUrl`
- `headline`
- `relationshipCapability`
- `chatAvailable`

### KD3：关系态直接来自 `RelationshipCapabilityView`

- 不在 App 再用布尔组合推导。
- 支持 `self / not_following / following / followed_by / mutual` 等能力矩阵。

### KD4：metadata / codegen 方案

- `user/user_profile/fields.yaml`
  - 新增 `SocialRelationSearchItemView`
- `user/user_profile/service.yaml`
  - 新增 `SearchSocialRelations`
- `_shared/request_context.yaml`
  - 新增该 operation 的 request page id

### KD5：迁移与兼容

- 现有 `SearchContacts` 保留给 chat 作为联系人/会话入口能力。
- 搜索 Journey 内不再用它承载“社交关系”。

## 字段演进、迁移/回填、必要时双读双写方案

- 结果项主键统一为 `profileSubjectId`。
- 历史 UI 中的 `userId` / `contactId` 仅保留适配期读取，不作为新结果模型主键。
- 不做双写；以 user 域搜索结果为唯一来源。

## feature flag、观测、SLO 验证与回滚方案

- 无业务 feature flag。
- 观测：
  - `social_relation_search_latency_ms`
  - `social_relation_result_click_count`
  - `social_relation_profile_open_failure_count`
- 回滚：
  - 整版回退，不恢复旧 chat 搜索节点

## TDD / ATDD 策略

- `T1_schema`：`SearchSocialRelations` DTO、relationship capability 映射
- `T2_module_interaction`：社交关系结果卡渲染与点击
- `T3_cross_service_integration`：user 搜索 + 关系态读取
- `T4_user_journey`：从搜索到用户主页

## plan slice 与 T1~T4 证据矩阵映射

| Slice | 目标 | 主要证据 |
|---|---|---|
| `P1` | 冻结 user 域社交关系搜索 contract | `T1_schema` |
| `P2` | 落地 app adapter 与结果项渲染 | `T2_module_interaction`, `T3_cross_service_integration` |
| `P3` | 验证从搜索进入主页与旧节点清理 | `T2_module_interaction`, `T4_user_journey` |

## 未来演进

- 若后续需要“社交关系 + 会话快捷操作”更强联动，可在 `SocialRelationSearchItemView` 上增加 action capability，而不回退到 chat contact 主导。
