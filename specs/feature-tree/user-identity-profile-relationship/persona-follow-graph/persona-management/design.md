# persona-management 设计方案

## 设计动因

`persona-management` 是整个 Journey 的 owner plane 起点。如果这里仍然保留 mock 管理页、真实子账号页、零散切换入口三套路径，后续的公开身份、上下文透传和 graph 都不会稳定。

本场景需要先冻结三件事：

1. owner 只能进入一个统一管理台。
2. 创建、切换、停用/删除保护都必须围绕 user 域 contract，而不是 UI 私有状态。
3. “删除分身”必须在空白分身删除与有历史分身退役之间有明确领域语义。

## 上游输入评审

| 输入 | 当前结论 |
|------|----------|
| `persona-management/spec.md` | owner plane、配额、切换、停用/删除保护边界清晰 |
| `persona-management/acceptance.yaml` | `A1/A2/A3/S1` 已明确，适合映射到 `P1~P4` |
| Journey `persona-follow-graph/design.md` | 已冻结统一 identity contract、管理台属于 owner plane |
| `owner-subaccount-homepage-unification/design.md` | 主页壳层不是本场景职责，管理台必须独立于公开主页 |
| 当前代码现状 | 已存在 `persona_management_page.dart` 与 `sub_account_management_page.dart` 两套路由/页面，需要收口 |

结论：

- `/design` 准入满足。
- 本场景优先级高于其它 Scenario 的 UI 接入，因为它决定 owner 如何选择 active persona。

## 对标输入分析

### 外部对标

| 对标对象 | 吸收点 | 不吸收点 |
|----------|--------|----------|
| 微信 | 默认不打扰单身份用户，但入口始终可找到 | 不照搬账号体系与通讯录入口 |
| 小红书 | 分身/创作身份作为管理平面的独立入口 | 不照搬创作者中心 IA |
| 微博 | 运营身份和公开身份分离 | 不照搬公开运营账号心智 |

### 内部对标

| 文档 / 能力 | 可复用点 |
|-------------|----------|
| Journey 设计 | `ActivePersonaContextView`、统一 route/provider 边界 |
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
- owner 视角的行为、埋点、错误恢复会长期漂移。
- 无法形成 Journey 级稳定入口。

### 方案 B：直接把公开主页编辑页扩成管理台

核心思路：

- 在公开主页或资料编辑页里内嵌分身列表与创建/切换能力。
- 不再保留独立管理台。

优点：

- 页面数更少。
- 入口表面上更“就近”。

缺点：

- owner plane 与 public plane 混杂。
- 容易把公开资料字段与 owner 私有管理字段混在一个 DTO 中。
- 删除/退役、配额、失败恢复都不适合放在公开资料页心智下。

### 方案 C：独立 owner plane 管理台 + 统一 user repository facade

核心思路：

- “我的主页”和设置页都进入同一个私有管理台 surface。
- user 域提供管理台所需的列表、配额、create/activate/retire/delete contract。
- App 侧用单一 provider/facade 组织状态，旧 mock 页只保留路由兼容壳。

优点：

- owner plane 与 public plane 清晰分离。
- 最符合当前 spec 与 Journey 设计。
- 便于做 feature flag、telemetry 和错误恢复。

缺点：

- 需要一次性收口 route、provider 与 contract。
- 旧页面需要迁移或降级为兼容壳。

## 选型决策

**选定方案：方案 C**

理由：

1. owner plane 必须是私有管理台，不能继续挂在公开资料语义下。
2. 只有方案 C 能让 `A1/A2/A3` 共享同一套列表、创建、切换、停用 contract。
3. 它允许先保留旧页面兼容入口，但真实行为全部收敛到单一 surface。

## 关键设计决策

### KD1：单一私有管理台 surface

- 入口一：`我的主页` 动作区。
- 入口二：设置页。
- 两个入口都跳到同一个私有 route / surface。
- 旧 `persona_management_page` 若继续存在，只作为兼容转发壳，不再承载业务逻辑。

### KD2：管理台 contract 冻结在 `user_profile` metadata

建议在 `contracts/metadata/user/user_profile/` 中补齐：

- `ListOwnerPersonas`
- `CreateSubAccount`
- `ActivateSubAccount`
- `RetireSubAccount`
- `DeleteEmptySubAccount`
- `GetPersonaManagementSummary`

建议新增或明确的实体：

- `PersonaManagementItemView`
- `PersonaManagementQuotaView`
- `PersonaLifecycleGuardView`

其中 `PersonaManagementItemView` 至少包含：

- `profileSubjectId`
- `subAccountId`
- `displayName`
- `isPrimary`
- `isActive`
- `isolationLevel`
- `inheritsFromOwner`
- `purposeHint`
- `hasAttributedHistory`
- `lastActivatedAt`

### KD3：创建与激活必须是可恢复的 owner plane 事务

- 创建分身成功后返回 `PersonaManagementItemView + canActivateNow`。
- “立即切换”是显式 follow-up 动作，不与创建成功语义混淆。
- 若创建成功但激活失败，系统必须保留“已创建但仍停留原 active persona”的明确状态。
- active persona exclusivity 在 user 域达成，不依赖 UI 自己比对列表。

### KD4：删除与退役双语义

- `hasAttributedHistory == false` 时允许 `DeleteEmptySubAccount`
- `hasAttributedHistory == true` 时进入 `RetireSubAccount`
- 主分身、最后一个剩余分身、仍处于 active 状态但无替代分身的场景都必须被 lifecycle guard 拦截

guard 不直接暴露底层风控或审计细节，只返回可执行语义：

- `allowed`
- `blocked_primary_persona`
- `blocked_last_persona`
- `blocked_active_persona`
- `retire_instead_of_delete`

### KD5：App 侧统一 management facade

App 不直接让多个页面各自拼 repository 返回值，而是统一通过管理台 facade/provider 输出：

- 列表状态
- 当前 active persona
- quota 状态
- create / activate / delete / retire command 状态
- 恢复建议和错误提示

这样可以保证：

- 主页入口和设置入口看到同一状态
- 单分身用户不会被多处逻辑强提示打扰
- telemetry 与 rollback 行为只需要收在一个状态中心

### KD6：失败恢复与可观测性内建

管理台至少记录：

- `persona_management_create_failed`
- `persona_management_activate_failed`
- `persona_management_delete_blocked`
- `persona_management_quota_reached`
- `persona_management_retired_count`

任何失败都必须满足：

- active persona 不被误切换
- 列表不会出现半成品分身
- 用户可看到明确恢复动作

## metadata / codegen 方案

顺序：

1. 在 `user_profile` metadata 增补管理台 list/summary/guard/command contract
2. 运行 `verify-metadata -> codegen -> codegen-app`
3. App 改为只消费生成的 DTO、path builder、operation 常量

要求：

- route / surface / operation 不允许在页面里硬编码第二套名称
- 删除/退役错误码必须来自 metadata，而不是 Widget 内字符串分支

## 字段演进、迁移/回填与兼容

- 保留 `SubAccount` 作为兼容命名，但新设计文档与新 contract 优先使用 `PersonaManagement*` / `profileSubjectId`
- 旧 mock 页保留为跳转壳，退出条件是所有入口都只访问统一管理台
- 对已有分身补齐 `hasAttributedHistory`、`isPrimary`、`isActive` 等管理视图字段

本场景不需要长期双写，只需要：

- 读时兼容旧 `SubAccount` DTO
- 写时统一走新 command contract

## feature flag、观测、SLO 验证与回滚方案

建议开关：

- `ops.user.persona_management_v1`

关键观测：

- 入口到达率
- create success / fail
- activate success / fail
- quota reached
- retire vs delete 分流占比

回滚策略：

- 关闭开关后退回单 active persona 安全基线
- 已创建的分身和历史归因不回滚
- 统一管理台可临时隐藏创建/退役动作，但仍允许读取列表

## TDD / ATDD 策略

- `T1_schema`
  - management entity、quota、guard、错误码、operation contract
- `T2_module_interaction`
  - 主页入口/设置入口共用同一管理台 state
  - create/activate/delete/retire 状态机
- `T3_cross_service_integration`
  - owner create/activate 与 user 域 active persona 真相源一致
- `T4_user_journey`
  - 单分身、达到配额、主分身删除阻断、空白分身删除、有历史分身退役

## plan slice 与 T1~T4 证据矩阵映射

| Slice | 目标 | 对应验收 | 主要证据 |
|-------|------|----------|----------|
| `P1` | 冻结管理台 metadata、route 与 quota/guard contract | `A1/A2` | `T1_schema` |
| `P2` | 建立 codegen 与统一 management facade 基线 | `A1/A2` | `T1_schema`, `T2_module_interaction` |
| `P3` | 落地 create/activate/delete/retire 主链路 | `A2/A3` | `T2_module_interaction`, `T3_cross_service_integration` |
| `P4` | 验证 feature flag、telemetry、rollback 与 owner journey | `A3/S1` | `T3_cross_service_integration`, `T4_user_journey` |

## 未来演进

- 当管理台稳定后，再单开 Story 清理旧 `persona_management_page` 命名和路由残留。
- 若未来引入更高配额或团队协作身份，也应继续落在 owner plane，不回到公开主页入口。
