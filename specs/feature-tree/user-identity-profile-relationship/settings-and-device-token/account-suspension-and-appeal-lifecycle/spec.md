# L3 Story：账号封禁、恢复与申诉生命周期 (`account-suspension-and-appeal-lifecycle`)

> 所属能力：[`settings-and-device-token`](../spec.md)
>
> Journey / Scenario：[`JNY-001 / SCN-004`](../../../spec.md#scn-004)
>
> 设计归属：[L2 DEC-001](../design.md#dec-001)

## 1. 用户价值

作为管理账号、Persona 或关系的用户，我希望验证受信运营决策驱动的可逆账号限制、认证拒绝、跨域 restriction projection 和申诉恢复，从而安全地维持身份、画像与关系状态。

## 2. 范围与非目标

### In Scope

- UserAccount active↔suspended 状态机、auth epoch、session/refresh revoke 与 durable outbox。
- moderation_case / appeal_case 审批 decision、审计链和 closed 不可恢复规则。
- Content（含推荐候选与读取路径）、Chat、Circle、Notification、Search 的可逆 restriction projection。
- Recommendation Service 只负责无账号私有状态的评分，不建立重复的账号事件 consumer；Content 必须在调用评分前排除受限候选。
- App 结构化受限说明、申诉续接、安全落点与恢复后新会话目标续接。

### Out of Scope

- 自动处罚策略、审核证据采集 UI、人工审核工作台信息架构。
- 任何 closed 账号、注销数据或已吊销 token 的恢复。

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 受信 Suspend decision 原子限制账号并撤销旧凭证

- 受信 `Suspend` decision 必须在同一事务更新账号状态与 auth epoch、撤销 session/refresh 并写入单一 outbox；事件不得携带 PII 或审核证据。

<a id="req-002"></a>
### REQ-002 登录、refresh 与服务鉴权一致拒绝封禁或旧 epoch 凭证

- 登录、refresh、owner/persona API 和长连接鉴权必须一致拒绝 suspended 账号或旧 auth epoch 凭证。

<a id="req-003"></a>
### REQ-003 申诉获批 Restore decision 仅恢复可逆受限态

- `Restore` 只能恢复 suspended 账号并递增 auth epoch；下游 restriction projection 必须幂等重放并在目标窗口内收敛。

<a id="req-004"></a>
### REQ-004 受限用户获得安全解释、申诉续接与恢复后新会话目标续接

- App 必须展示安全的 `account_suspended` 解释与申诉续接，不泄露审核详情；恢复后必须重新登录才能继续原目标。
- 申诉认领 tuple 的 accountId 必须由 UserAccount 当前 canonical identity parser 严格验证；版本段、旧编码、别名编码或无法证明 routing shard 的值必须拒绝，不得双读或 fallback。

<a id="req-005"></a>
### REQ-005 `UserAccount` 的 `active → suspended → active` 唯一可逆状态机，及 `closed` 不可恢复

- `UserAccount` 仅允许 `active → suspended → active` 可逆迁移；`closed` 不可恢复。
- 受限面关闭后必须回到安全首页；恢复后旧 token 保持失效，仅新会话可续接原目标。
- 生产恢复操作只允许具备审批权限的受信 operator 执行，并必须绑定审计与可回滚发布版本。

## 4. 契约引用

- canonical：`quwoquan_service/services/user-service/contracts/account/user_account`
- canonical：`quwoquan_service/services/user-service/contracts/account/account_appeal_intake`
- canonical：`quwoquan_service/contracts/metadata/_control_plane/product/workflow.yaml`
- canonical：`quwoquan_service/contracts/metadata/_control_plane/product/audit_schema.yaml`
- canonical：`quwoquan_service/services/user-service/contracts/account/account_session`
- canonical：`quwoquan_service/services/user-service/contracts/account/user_account/errors.yaml`
- canonical：`quwoquan_service/services/user-service/contracts/account/user_account/events.yaml`
- canonical：`specs/feature-tree/user-identity-profile-relationship/settings-and-device-token/account-suspension-and-appeal-lifecycle/spec.md`

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 受信 Suspend decision 原子限制账号并撤销旧凭证

- GIVEN UserAccount 处于 active，存在多个 active session/refresh binding。
- GIVEN moderation_case 已满足审批与审计要求，Product Ops 持有已签发的 Suspend decision。
- WHEN User Service 接收同一 decision 的首次提交、重放或冲突 digest。
- THEN 首次提交在同一事务写入 suspended、authEpoch、session revoke receipt 与单一 UserSuspended outbox。
- THEN 同 decision 重放返回稳定 receipt；相同 decision id 不同 digest、非受信主体或 closed 目标均 fail-closed。

<a id="gwt-002"></a>
### GWT-002 登录、refresh 与服务鉴权一致拒绝封禁或旧 epoch 凭证

- GIVEN Suspend transaction 已成功提交，攻击者持有提交前 access token、refresh token 或长连接凭证。
- WHEN 攻击者尝试登录、refresh、请求 owner/persona API 或续期长连接。
- THEN 所有入口返回 metadata 定义的 account_suspended 或 token epoch 结构化失败，绝不降级到旧 session。
- THEN enforcement reader 不可用或读取状态未知时 fail-closed。

<a id="gwt-003"></a>
### GWT-003 申诉获批 Restore decision 仅恢复可逆受限态

- GIVEN UserAccount 处于 suspended，下游 restriction projection 已收敛。
- GIVEN appeal_case 已批准且产生受信 Restore decision。
- WHEN User Service 接收 Restore，消费者重放 UserRestored，用户重新登录。
- THEN accountState 恢复 active、authEpoch 递增、旧 session 保持撤销；下游恢复后续可见性/写入/投递。
- THEN 已删除或匿名化的 closed 数据不被恢复
- AND 过期通知不补发
- AND 所有 consumer 保持 inbox/digest 幂等。

<a id="gwt-004"></a>
### GWT-004 受限用户获得安全解释、申诉续接与恢复后新会话目标续接

- GIVEN Gamma 真实设备上的账号已经由受信 decision 进入 suspended，且存在受保护目标 continuation。
- WHEN 用户尝试进入 App、提交申诉并在批准后重新登录。
- THEN App 展示结构化 account_suspended 解释与申诉/支持入口，不泄露 reason、evidence、case 或原始异常。
- THEN 关闭受限面回安全首页；Restore 后旧 token 不可用，新会话继续原目标且主页/内容可见性一致恢复。

## 6. 依赖

- 前置要求：[`settings-and-device-token`](../spec.md) 的范围、要求与 SIT。
- 下游结果：本 Story 声明的 GWT 可观察结果。
- 父级设计：[L2 DEC-001](../design.md#dec-001)

## 7. 开放事项

<a id="open-001"></a>
### OPEN-001 受信 Suspend decision 原子限制账号并撤销旧凭证

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：仍缺 Product Ops 从已审批 workflow 生成受信 decision、调用 User 并持久化 application receipt 的生产链路；User Service 的状态、epoch、session revoke、outbox 同事务与事件脱敏已有直接证据。
- 完成判定：`GWT-001` 对应行为满足且真实测试 `spec_ref` 有效

<a id="open-002"></a>
### OPEN-002 登录、refresh 与服务鉴权一致拒绝封禁或旧 epoch 凭证

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺少覆盖全部认证入口和旧 token 拒绝窗口的同源直接证据。
- 完成判定：`GWT-002` 对应行为满足且真实测试 `spec_ref` 有效

<a id="open-003"></a>
### OPEN-003 申诉获批 Restore decision 仅恢复可逆受限态

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：仍缺全部消费者 codegen/gate 收敛、retry/DLQ 与目标窗口收敛证据；Content（含推荐候选与读取路径）、Chat、Circle、Notification、Search 已具备可逆投影与部分重放/冲突证据。Recommendation Service 无账号私有状态，不建立重复投影。
- 完成判定：`GWT-003` 对应行为满足且真实测试 `spec_ref` 有效

<a id="open-004"></a>
### OPEN-004 正式申诉 intake、单用途身份凭据与官方续接入口

- 类型：`capability_gap`
- 优先级：`P0`
- 准出影响：`block`
- 影响或价值：仍缺四环境不可变官方 Web release/HTTPS URL、生产 OTP material、客服 owner/SLA、Provider/Widget、Gamma Android/iOS UAT 与受保护 Prod receipt，因此公开 Issue/Submit operation 继续 `blocked`，不得宣称端到端申诉已商用。仓内已具备 User 领域拥有的 identity-bound `AccountAppealIntake` 聚合、手机号 challenge 与 active binding 核验、十分钟单用途摘要凭据、按 suspension auth epoch 唯一的幂等提交、180 天保留/删除、真实 PostgreSQL/HTTP API integration 以及 Product Ops 精确 tuple 认领；`ClaimAccountAppealIntake` 仅代表内部认领边界已实现。
- 完成判定：User 领域声明 canonical submission operation，并以完成手机号或受信联合身份挑战后签发的短时、单用途、绑定账号与环境且不可充当 access token 的凭据接收幂等提交。契约同时冻结滥用频控、隐私分类、保留/删除、审计与客服交接口径。四环境官方 HTTPS 申诉 URL 绑定不可变 Web release，并明确运营 owner 与处置 SLA。Product Ops 只消费 opaque `intakeRef`。`GWT-004` 的 local_contract、api_integration、Provider、Widget、Gamma Android/iOS user_acceptance 与受保护 Prod 操作均以真实 receipt 通过。
- 依赖：身份与安全评审、隐私保留口径、官方 Web 发布 owner、客服值班与处置 SLA。
