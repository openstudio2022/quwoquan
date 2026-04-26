# persona-management 设计方案

## 设计动因

`persona-management` 是整个 Journey 的用户私有管理面起点。如果这里仍然保留 mock 管理页、真实子账号页、零散切换入口三套路径，后续的公开分身资料、上下文透传和 graph 都不会稳定。

本场景需要先冻结四件事：

1. 用户只能进入一个统一管理台。
2. 创建、切换、继承/同步建议、停用/删除保护都必须围绕 user 域 contract，而不是 UI 私有状态。
3. “删除分身”必须在空白分身删除与有历史分身退役之间有明确领域语义。
4. `displayName / userHandle / phone / email` 的默认继承与跨分身同步建议必须成为管理面正式职责。

## 上游输入评审

| 输入 | 当前结论 |
|------|----------|
| `persona-management/spec.md` | 用户管理面、配额、切换、继承/同步建议、停用/删除保护边界清晰 |
| `persona-management/acceptance.yaml` | `A1/A2/A3/S1` 已明确，适合映射到 `P1~P4` |
| Journey `persona-follow-graph/design.md` | 已冻结统一 `userId / personaId / userHandle` contract，管理台属于用户私有管理面 |
| `owner-subaccount-homepage-unification/design.md` | 主页壳层不是本场景职责，管理台必须独立于公开主页 |
| 当前代码现状 | 统一管理台、feature flag 与 create/activate/sync 契约已落地；剩余风险集中在 `retire` 持久化、`hasAttributedHistory` 真值来源与 `delete-empty` 真实空分身校验 |

结论：

- `/design` 准入满足。
- 本场景优先级高于其它 Scenario 的 UI 接入，因为它决定用户如何选择 active persona。

## 对标输入分析

### 外部对标

| 对标对象 | 吸收点 | 不吸收点 |
|----------|--------|----------|
| 微信 | 默认不打扰单分身用户，但入口始终可找到 | 不照搬账号体系与通讯录入口 |
| 小红书 | 分身/创作身份作为管理平面的独立入口 | 不照搬创作者中心 IA |
| 微博 | 运营身份和公开身份分离 | 不照搬公开运营账号心智 |

### 内部对标

| 文档 / 能力 | 可复用点 |
|-------------|----------|
| Journey 设计 | `ActivePersonaContextView`、统一 route/provider 边界、`personaId / userHandle` 收敛 |
| `app_router.dart` 与 metadata route 原则 | 管理台必须成为单一私有 surface，不走公开 path |
| `sub_account_management_page` 现有实现 | 作为真实数据链路改造基础，而不是继续保留 mock 页 |

## 方案对比

### 方案 A：保留 mock 页与真实页双入口，逐步替换

核心思路：

- 先继续让“我的主页”指向 mock 页。
- 设置页或隐藏路径使用真实管理页。
- 后续再慢慢把能力搬过去。

优点：

- 短期改动最小。
- 不必立即调整现有路由。

缺点：

- 继续制造双真相源。
- 用户管理面的行为、埋点、错误恢复会长期漂移。
- 无法形成 Journey 级稳定入口。

### 方案 B：直接把公开主页编辑页扩成管理台

核心思路：

- 在公开主页或资料编辑页里内嵌分身列表与创建/切换能力。
- 不再保留独立管理台。

优点：

- 页面数更少。
- 入口表面上更“就近”。

缺点：

- 用户私有管理面与 public plane 混杂。
- 容易把公开资料字段与私有管理字段混在一个 DTO 中。
- 删除/退役、配额、同步建议与失败恢复都不适合放在公开资料页心智下。

### 方案 C：独立用户私有管理台 + 统一 user repository facade

核心思路：

- “我的主页”和设置页都进入同一个私有 route / surface。
- user 域提供管理台所需的列表、配额、create/activate/retire/delete/sync contract。
- App 侧用单一 provider/facade 组织状态，旧 mock 页与旧 sub-account 页都不再作为兼容壳保留。

优点：

- 用户私有管理面与 public plane 清晰分离。
- 最符合当前 spec 与 Journey 设计。
- 便于做 feature flag、telemetry 和错误恢复。

缺点：

- 需要一次性收口 route、provider 与 contract。
- 旧页面需要迁移或直接删除。

## 选型决策

**选定方案：方案 C**

理由：

1. 用户私有管理面必须是独立管理台，不能继续挂在公开资料语义下。
2. 只有方案 C 能让 `A1/A2/A3` 共享同一套列表、创建、切换、停用和同步 contract。
3. 在本次“不保留兼容层”的前提下，方案 C 可以直接把旧页面和旧命名一次性替换到单一 surface。

## 关键设计决策

### KD1：单一私有管理台 surface

- 入口一：`我的主页` 动作区。
- 入口二：设置页。
- 两个入口都跳到同一个私有 route / surface。
- 不保留旧 `persona_management_page` / `sub_account_management_page` 双页面并存形态；最终只保留一套分身管理页面。

### KD2：管理台 contract 冻结在 `user_profile` metadata

建议在 `contracts/metadata/user/user_profile/` 中补齐或重写：

- `ListPersonas`
- `CreatePersona`
- `ActivatePersona`
- `RetirePersona`
- `DeleteEmptyPersona`
- `GetPersonaManagementSummary`
- `ApplyPersonaProfileSync`

建议新增或明确的实体：

- `PersonaManagementItemView`
- `PersonaManagementQuotaView`
- `PersonaLifecycleGuardView`
- `PersonaSyncSuggestionView`

其中 `PersonaManagementItemView` 至少包含：

- `personaId`
- `displayName`
- `userHandle`
- `phone`
- `email`
- `isPrimary`
- `isActive`
- `isolationLevel`
- `inheritsFromPrimaryPersona`
- `purposeHint`
- `hasAttributedHistory`
- `lastActivatedAt`
- `inheritanceState`
- `lastSyncedAt`

### KD3：创建与激活必须是可恢复的用户私有事务

- 创建分身成功后返回 `PersonaManagementItemView + canActivateNow`。
- “立即切换”是显式 follow-up 动作，不与创建成功语义混淆。
- 若创建成功但激活失败，系统必须保留“已创建但仍停留原 active persona”的明确状态。
- active persona exclusivity 在 user 域达成，不依赖 UI 自己比对列表。
- 创建分身时若未显式填写 `phone / email`，默认复制主分身当前值并记录为继承态。

### KD4：删除与退役双语义

- `hasAttributedHistory == false` 时允许 `DeleteEmptyPersona`
- `hasAttributedHistory == true` 时进入 `RetirePersona`
- 主分身、最后一个剩余分身、仍处于 active 状态但无替代分身的场景都必须被 lifecycle guard 拦截

guard 不直接暴露底层风控或审计细节，只返回可执行语义：

- `allowed`
- `blocked_primary_persona`
- `blocked_last_persona`
- `blocked_active_persona`
- `blocked_retired_persona`
- `retire_instead_of_delete`

并把真实退役状态持久化到 Persona 聚合：

- `status = active | retired`
- `retiredAt`
- retired 后禁止继续作为新动作主体，但保留历史归因对象与审计链

### KD5：资料继承与同步建议

- 分身创建后默认处于“继承主分身资料”状态。
- 当任一分身修改 `displayName / userHandle / phone / email` 时，系统生成 `PersonaSyncSuggestionView`：
  - `sourcePersonaId`
  - `targetPersonaIds`
  - `changedFields`
  - `suggestedAt`
- 用户可选择：
  - 同步到全部分身
  - 同步到指定分身
  - 忽略
- 对已独立改写过的目标分身，执行同步前必须显示覆盖确认。

### KD6：App 侧统一 management facade

App 不直接让多个页面各自拼 repository 返回值，而是统一通过管理台 facade/provider 输出：

- 列表状态
- 当前 active persona
- quota 状态
- create / activate / delete / retire / sync command 状态
- 恢复建议和错误提示
- 待处理 sync suggestion 状态

这样可以保证：

- 主页入口和设置入口看到同一状态
- 单分身用户不会被多处逻辑强提示打扰
- telemetry 与 rollback 行为只需要收在一个状态中心

### KD7：失败恢复与可观测性内建

管理台至少记录：

- `persona_management_create_failed`
- `persona_management_activate_failed`
- `persona_management_delete_blocked`
- `persona_management_quota_reached`
- `persona_management_retired_count`
- `persona_management_profile_sync_suggested`
- `persona_management_profile_sync_applied`
- `persona_management_profile_sync_rejected`

任何失败都必须满足：

- active persona 不被误切换
- 列表不会出现半成品分身
- 用户可看到明确恢复动作

## metadata / codegen 方案

顺序：

1. 在 `user_profile` metadata 增补管理台 list/summary/guard/command/sync contract
2. 运行 `verify-metadata -> codegen -> codegen-app`
3. App 改为只消费生成的 DTO、path builder、operation 常量

要求：

- route / surface / operation 不允许在页面里硬编码第二套名称
- 删除/退役/同步错误码必须来自 metadata，而不是 Widget 内字符串分支

## 字段演进、迁移/回填与替换

- 本场景不保留 `SubAccount` 作为兼容命名，统一改写为 `Persona`
- 旧 mock 页与旧子账号页直接退出主链路，不保留跳转壳
- 对已有分身补齐 `personaId / userHandle / phone / email / hasAttributedHistory / isPrimary / isActive / inheritanceState` 等管理视图字段
- 本场景不采用双读双写：读写都统一走新 command contract

## feature flag、观测、SLO 验证与回滚方案

建议开关：

- `ops.user.persona_management_v1`
- `ops.user.persona_profile_sync_v1`

关键观测：

- 入口到达率
- create success / fail
- activate success / fail
- quota reached
- retire vs delete 分流占比
- profile sync suggested / applied / rejected

回滚策略：

- 关闭开关后退回单 active persona 安全基线
- 已创建的分身和历史归因不回滚
- 统一管理台可临时隐藏创建/退役/同步动作，但仍允许读取列表

## TDD / ATDD 策略

- `T1_schema`
  - management entity、quota、guard、sync、错误码、operation contract
- `T2_module_interaction`
  - 主页入口/设置入口共用同一管理台 state
  - create/activate/delete/retire/sync 状态机
- `T3_cross_service_integration`
  - create/activate 与 user 域 active persona 真相源一致
  - `displayName / userHandle / phone / email` sync suggestion contract 正常工作
- `T4_user_journey`
  - 单分身、达到配额、主分身删除阻断、空白分身删除、有历史分身退役、资料同步建议

## plan slice 与 T1~T4 证据矩阵映射

| Slice | 目标 | 对应验收 | 主要证据 |
|-------|------|----------|----------|
| `P1` | 冻结管理台 metadata、route、quota/guard 与 sync contract | `A1/A2` | `T1_schema` |
| `P2` | 建立 codegen 与统一 management facade 基线 | `A1/A2` | `T1_schema`, `T2_module_interaction` |
| `P3` | 落地 create/activate/delete/retire/sync 主链路 | `A2/A3` | `T2_module_interaction`, `T3_cross_service_integration` |
| `P4` | 验证 feature flag、telemetry、rollback 与用户 journey | `A3/S1` | `T3_cross_service_integration`, `T4_user_journey` |

## 未来演进

- 当管理台稳定后，可继续把更多资料字段纳入主分身继承/同步框架。
- 若未来引入更高配额或团队协作身份，也应继续落在用户私有管理面，不回到公开主页入口。
