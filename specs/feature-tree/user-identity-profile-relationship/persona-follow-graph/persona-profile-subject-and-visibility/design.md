# persona-profile-subject-and-visibility 设计方案

## 设计动因

如果 `persona-profile-subject-and-visibility` 不先收口，仓库会继续同时存在 `PersonaDto`、公开主页 DTO、内容作者快照、聊天头像字段等多套“作者是谁”的解释逻辑。这个场景的设计重点是把 user 域的公开身份冻结成统一 contract，让 profile/content/chat/circle/assistant 都只消费它。

本场景需要同时解决：

1. 公开身份到底是 `Persona` 本体、额外 `PublicProfile` 实体，还是 user 域合成读模型。
2. owner 基线、分身覆写、同步范围如何表达，避免 UI 私藏规则。
3. strict isolation 与 retired attribution 如何做到“公开最小暴露，但历史可稳定渲染”。

## 上游输入评审

| 输入 | 当前结论 |
|------|----------|
| `persona-profile-subject-and-visibility/spec.md` | 公开身份、继承/覆写、同步范围、可见性与历史归因边界清晰 |
| `persona-profile-subject-and-visibility/acceptance.yaml` | `A1/A2/A3/S1` 可直接映射到 `P1~P4` |
| Journey `persona-follow-graph/design.md` | 已冻结 `ProfileSubjectView` 与 `ActivePersonaContextView` 双轨 contract |
| `owner-subaccount-homepage-unification/design.md` | 主页是本场景 contract 的消费方，不再主定义 persona 公开身份 |
| 现有 user/content/chat 契约 | 已有 persona 相关字段预埋，但尚未统一到 `profileSubjectId` 主键 |

结论：

- `/design` 准入满足。
- 本场景应优先于主页 UI 改造落地，因为主页、内容卡、评论、聊天都依赖它的读模型。

## 对标输入分析

### 外部对标

| 对标对象 | 吸收点 | 不吸收点 |
|----------|--------|----------|
| 小红书 | 作者主页与内容作者卡使用同一公开身份 | 不照搬创作者中心信息层级 |
| 抖音 | 公开可见性与隐私语义清晰分层 | 不照搬强内容导向路由 |
| 微信 | 管理平面与应用主体分离 | 不照搬实名资料体系 |

### 内部对标

| 文档 / 能力 | 可复用点 |
|-------------|----------|
| Journey 设计 | `ProfileSubjectView` 是公开读模型，不暴露 owner 映射 |
| `owner-subaccount-homepage-unification` | 主页首屏、按钮矩阵、资料编辑都应消费 user 域 contract |
| `content-display-journey-consistency` | canonical key 与读模型消费优先级 |

## 方案对比

### 方案 A：新增独立 `PublicProfile` 物化实体

核心思路：

- owner 和 persona 都额外映射到一张 `PublicProfile`。
- 主页、内容卡、评论、聊天都读取这张实体。

优点：

- 下游读取简单。
- 首屏聚合方便。

缺点：

- 引入第三套身份实体。
- owner 基线、persona override 需要长期双写。
- 与当前产品语义“作者分身仍是 user 域 Persona 的产品化表面”冲突。

### 方案 B：user 域合成 `ProfileSubjectView` 读模型，owner 只提供基线，persona 只保存覆写

核心思路：

- `UserProfile` 保存 owner 基线。
- `Persona` 只保存 override 字段和可见性。
- 对外统一合成 `ProfileSubjectView`。

优点：

- 与 DDD 和 PRD 完全一致。
- 不需要长期双写 public profile 副本。
- 对停用、strict isolation、历史归因的治理更清晰。

缺点：

- user 域读取逻辑更复杂。
- 需要设计好缓存与回填。

### 方案 C：继续使用 `PersonaDto`，由 App 侧组合 owner 基线与公开字段

核心思路：

- 服务端保持现状。
- App 在 provider 中拼 `PersonaDto + UserProfileDto`。

优点：

- 服务端改动小。
- 短期页面能先跑起来。

缺点：

- 再次把公开身份规则放回 UI。
- content/chat/assistant 无法复用。
- 与 metadata-first 原则冲突。

## 选型决策

**选定方案：方案 B**

理由：

1. 它维持 `Persona` 仍归 user 域聚合，不引入第三套公开身份实体。
2. 它让同步范围、override、可见性都能成为正式 contract，而不是 UI 私有逻辑。
3. 它最适合支撑 retired attribution 与 strict isolation 的长期演进。

## 关键设计决策

### KD1：`ProfileSubjectView` 是唯一公开身份真相源

所有公开读取统一消费 `ProfileSubjectView`，至少包含：

- `profileSubjectId`
- `subjectType`
- `subAccountId`
- `username`
- `displayName`
- `avatarUrl`
- `backgroundUrl`
- `bio`
- `profileVisibility`
- 统计字段

明确禁止：

- 公开主页首屏直接消费 `PersonaDto`
- 评论、内容卡、聊天列表直接拼 owner 字段
- 普通接口返回 owner 管理字段

### KD2：owner 基线 + persona override，而不是完整副本

owner 基线保存在 `UserProfile`，persona 只保存覆写字段：

- `displayName`
- `avatarUrl`
- `backgroundUrl`
- `bio`
- `profileVisibility`

对应新增：

- `ProfileInheritanceStateView`
  - `inheritsFromOwner`
  - `overriddenFields`
  - `lastSyncSource`
  - `lastSyncAt`

这保证：

- 默认继承成立
- override 最小化
- 后续字段扩展不需要整份 public profile 双写

### KD3：写入 contract 必须显式携带同步范围

建议冻结 `ProfileSubjectMutation`：

- `displayName`
- `avatarUrl`
- `backgroundUrl`
- `bio`
- `profileVisibility`
- `applyScope`
- `syncTargetIds`
- `fieldsMask`

`applyScope` 至少支持：

- `current_subject_only`
- `owner_only`
- `all_sub_accounts`
- `selected_subjects`

这样同步语义由 user 域 contract 保证，而不是由 UI 自己猜。

### KD4：可见性与 retired attribution 分层

公开可见性冻结为：

- `open`
- `semi`
- `strict`

语义：

- `strict` 仅影响公开读取，不影响 owner 管理和审计。
- retired persona 默认不再作为新动作主体，但历史对象继续使用不可变作者快照。
- “公开主页是否还能访问”与“历史对象是否还能渲染”是两条独立规则。

### KD5：路由继续使用 `username`，内部 key 统一使用 `profileSubjectId`

对外：

- 路由仍可保持 `/user/{username}`

对内：

- Repository / provider / graph / context 一律使用 `profileSubjectId`
- `username` 只承担 URL 和展示职责

这可以避免 username 变更时内部引用漂移。

### KD6：消费边界必须统一

消费方只允许使用以下 contract：

- 主页：`ProfileSubjectView`
- 内容/评论：`profileSubjectId + author snapshot`
- 聊天：`profileSubjectId + sender snapshot`
- assistant：只读取公开允许字段与 typed persona context

不允许：

- content/chat/circle/assistant 复制一套 `ProfileSubject` 合成逻辑
- UI 根据 owner + persona 自行推导 strict/semi/open

## metadata / codegen 方案

主目录固定为 `contracts/metadata/user/user_profile/`，建议补齐：

- `ProfileSubjectView`
- `ProfileSubjectMutation`
- `ProfileInheritanceStateView`
- `ListProfileSubjects`
- `GetProfileSubject`
- `UpdateProfileSubject`

下游配合：

- `content/post` 与 `messages/conversation` 补齐 `profileSubjectId` 和 snapshot 字段
- `make -C quwoquan_service verify-metadata`
- `make codegen`
- `make codegen-app`

App、service、cloud client 全部改为消费生成 DTO 和 path builder。

## 字段演进、迁移/回填与兼容

### 字段演进

- 新写链路统一补齐 `profileSubjectId`
- `PersonaDto` 保留为管理视角兼容模型，不再作为公开首屏模型
- 旧字段优先级：
  - 新对象读 `ProfileSubjectView`
  - 兼容对象读 `PersonaDto`，再映射成 `ProfileSubjectView`

### 回填

- 为现有分身补齐 `profileSubjectId`
- 对现有 persona 计算 override 字段与 owner 基线差异
- 为历史对象补齐可读取的作者快照映射，不重写历史主体

### 兼容退出条件

- 主页、内容卡、评论、聊天、graph list 全部以 `ProfileSubjectView` 为主
- 端侧不再直接拿 `PersonaDto` 渲染公开作者身份

## feature flag、观测、SLO 验证与回滚方案

建议开关：

- `ops.user.profile_subject_v1`

关键观测：

- `profile_subject_public_read_latency_ms`
- `profile_subject_visibility_not_found_count`
- `retired_subject_attribution_fallback_count`
- `profile_subject_sync_scope_submit_count`

回滚原则：

- 关闭开关后，可退回旧公开读取路径
- 已生成的 `profileSubjectId` 和历史快照不删除
- retired attribution 不允许回滚到 owner 重绑

## TDD / ATDD 策略

- `T1_schema`
  - `ProfileSubjectView / Mutation / InheritanceState` schema
  - visibility 枚举与错误码
- `T2_module_interaction`
  - 主页、资料编辑、同步范围提示、consumer adapter
- `T3_cross_service_integration`
  - profile/content/chat 统一读取 `ProfileSubject`
  - retired persona 历史渲染回归
- `T4_user_journey`
  - 编辑 owner 基线、编辑 persona override、strict isolation 公开读取、retired persona 历史浏览

## plan slice 与 T1~T4 证据矩阵映射

| Slice | 目标 | 对应验收 | 主要证据 |
|-------|------|----------|----------|
| `P1` | 冻结 `ProfileSubject`、visibility 与 inheritance metadata | `A1/A3` | `T1_schema` |
| `P2` | 建立 codegen 与公开身份兼容读取基线 | `A1/A2` | `T1_schema`, `T3_cross_service_integration` |
| `P3` | 落地 mutation、sync scope、retired attribution 逻辑 | `A2/A3` | `T2_module_interaction`, `T3_cross_service_integration` |
| `P4` | 验证 consumer、telemetry、rollback 与用户旅程 | `A1/A3/S1` | `T2_module_interaction`, `T4_user_journey` |

## 未来演进

- 当所有公开消费端都切到 `ProfileSubjectView` 后，再单开 Story 清理旧 `PersonaDto` 公共消费路径。
- 若后续扩展更多可覆写字段，仍沿用 owner 基线 + persona override，不新增 `PublicProfile` 物化实体。
