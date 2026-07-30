# L3 Story：账号治理审核、申诉复核与执行投递 (`account-moderation-and-appeal-enforcement`)

> 所属能力：[`product-control-plane-foundation`](../spec.md)
>
> 协作 Journey / Scenario：[`JNY-001 / SCN-004`](../../../spec.md#scn-004)
>
> 设计归属：[L2 DEC-001](../design.md#dec-001)

## 1. 用户价值

作为具备明确权限的治理运营人员，我希望账号暂停与申诉恢复由同一个可审计 case 聚合完成双人复核、签发不可变决定并可靠交付给 UserAccount，从而既不由后台页面直接改账号，也不因超时、并发或重试产生重复处罚、错误恢复或不可追溯状态。

## 2. 范围与非目标

### In Scope

- Product Ops 拥有唯一 `AccountEnforcementCase` 聚合；`moderation` 与 `appeal` 是显式 case 类型，共享同一审批、决定、投递与恢复状态机。
- moderation 只可派生 `Suspend`，appeal 只可派生 `Restore`；动作不接受调用方自由输入。
- 两名不同受信 operator 批准、任一拒绝关闭、命令幂等、不可变 decision、持久化 HTTP outbox、UserAccount application receipt、bounded retry、无 PII terminal DLQ 与同 decision 恢复。
- Product Ops 只通过 User Service 的公开 internal Suspend/Restore command 改变账号状态，不直写 UserAccount 存储。

### Out of Scope

- `UserAccount active ↔ suspended`、auth epoch、session/refresh revoke 及跨域 restriction projection；这些事实仍由 User 领域及其消费者拥有。
- 用户申诉提交 operation、正式申诉 URL、审核证据采集 UI、自动处罚策略和运营工作台信息架构。
- `closed` 账号、注销数据或已吊销凭据的恢复。

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 moderation 双人复核原子签发唯一 Suspend decision

- 创建、审核与恢复命令必须使用稳定 `Idempotency-Key`；同键同摘要返回原命令的稳定结果，同键不同摘要 fail-closed。
- case 创建者与证据仅保留在 Product Ops；两个不同受信 reviewer 批准后，case 终态、第二份 review、不可变 decision、命令 receipt 与 durable HTTP outbox 必须在同一 PostgreSQL transaction 提交。
- reviewer 不提交聚合版本；服务端在事务内锁定并比较当前版本，只对纯并发冲突做有界重试。
- 任一 reject 立即关闭且不签发 decision；同一 reviewer 不得再次审核，已关闭 case 不得复开或追加决定。

<a id="req-002"></a>
### REQ-002 appeal 仅从正式 intake 与最新已交付 Suspend decision 签发 Restore

- appeal 必须同时引用既有正式 `intakeRef` 与同账号最新已成功交付的 Suspend decision；缺失、过期、跨账号或存在未解决投递时 fail-closed。
- Restore 仍需两名不同 reviewer 批准；不得因“打开申诉 case”宣称 suspended 用户已经提交申诉。
- dispatcher 只能用受限服务身份和最小 decision wire 调用 UserAccount；不得发送 reviewer、evidence 或 intake。
- 临时失败采用有界指数退避；永久失败或次数耗尽写入只含 decision id、retry generation、error class、attempt count 与时间的 terminal DLQ，并使 readiness 失败。
- 人工恢复只能增加 retry generation 并重置同一 decision；不得签发替代 decision、修改摘要或建立消息/同步调用双轨。

<a id="req-003"></a>
### REQ-003 生产装配、权限与观测必须 fail-closed

- operator OIDC、operation scope、Product Ops → UserAccount 服务身份、PostgreSQL、UserAccount authority URL、timeout、lease、重试与 pending-age 配置缺失或无效时，环境装配必须失败。
- 指标只允许固定 `operation/action/outcome/state` 维度；日志、metric label 与 terminal DLQ 不得包含 account、reviewer、evidence、intake、token 或原始 payload。
- SLO、pending age、terminal DLQ、恢复演练和 UserAccount receipt 必须共同进入 Gamma/Prod 准出证据；单元测试或本地 fake 不能替代真实环境验收。

## 4. 契约引用

- canonical：`quwoquan_service/services/product-ops-service/contracts/product_ops/account_enforcement_case/object.yaml`
- canonical：`quwoquan_service/services/product-ops-service/contracts/product_ops/account_enforcement_case/fields.yaml`
- canonical：`quwoquan_service/services/product-ops-service/contracts/product_ops/account_enforcement_case/operations.yaml`
- canonical：`quwoquan_service/services/product-ops-service/contracts/product_ops/account_enforcement_case/errors.yaml`
- canonical：`quwoquan_service/services/product-ops-service/contracts/product_ops/account_enforcement_case/storage.yaml`
- cross-domain command：`quwoquan_service/services/user-service/contracts/account/user_account`
- cross-domain intake：`quwoquan_service/services/user-service/contracts/account/account_appeal_intake`

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 moderation 双人复核原子签发并可靠交付 Suspend decision

- GIVEN 受信 operator 以有效幂等键为 active 账号创建 moderation case，且提供 policy 与受控 evidence refs。
- WHEN 同一创建命令被重放、同键发生摘要漂移、两个不同 reviewer 并发或顺序批准、相同 reviewer 重复审核，或任一 reviewer 拒绝。
- THEN 同键同摘要返回原命令稳定结果，同键不同摘要返回 canonical conflict；调用方不提供 `If-Match`，服务端锁定当前状态并解决纯并发竞争。
- THEN 两名不同 reviewer 批准时，在一个真实 PostgreSQL transaction 中只产生一个 approved case、两份 review、一个不可变 Suspend decision、一个 command receipt 与一个待投递 outbox；任一 reject 关闭 case 且不产生 decision。
- THEN dispatcher 仅以 `decisionId` 作为 UserAccount 幂等键发送 canonical Suspend wire，成功后持久化 application receipt；重放不得改变 decision id 或摘要。

<a id="gwt-002"></a>
### GWT-002 appeal 前置校验、同 decision 恢复与无 PII terminal DLQ

- GIVEN 同账号最新 Suspend decision 已成功交付，且运营人员持有来自正式申诉入口的 `intakeRef`；或某一待交付 decision 已进入 terminal DLQ。
- WHEN 两名不同 reviewer 批准 appeal、旧 Suspend decision 被再次引用、UserAccount 返回永久失败，或受信 operator 对 terminal DLQ 发起幂等恢复。
- THEN 有效 appeal 只签发一个 Restore decision；过期 source decision、缺失 intake、存在未解决投递或冲突摘要均 fail-closed。
- THEN 永久失败或重试耗尽使 readiness 失败，terminal DLQ schema 不含账号、证据、intake、审核人或 payload。
- THEN 恢复只递增 retry generation 并重新投递原 decision；UserAccount path、idempotency key、case ref、decision digest 与 approved time 保持不变，成功 receipt 后 readiness 恢复。

<a id="gwt-003"></a>
### GWT-003 Gamma 真实权限、双签、跨域收敛与恢复演练

- GIVEN Gamma 使用真实 operator OIDC、细分 operation scope、Product Ops 服务身份、PostgreSQL、User Service Remote composition 和真实可逆测试账号。
- WHEN 执行 moderation → Suspend → 旧 token 拒绝 → 正式 appeal intake → Restore → 新会话登录，并注入一次可恢复投递失败和一次 terminal DLQ。
- THEN Product Ops case/decision/receipt、UserAccount state/auth epoch/session revoke、下游 restriction projection、App 受限与恢复体验、指标/告警/DLQ/恢复记录可由同一 trace 与 decision ref 对齐。
- THEN 未获授权 scope、OIDC/服务身份无效、依赖不可用或 DLQ 未清零时全部 fail-closed，且不得以本地 fake、人工改库或 Mock App 作为替代证据。

## 6. 依赖

- 前置要求：[`product-control-plane-foundation`](../spec.md) 的范围、要求与 SIT。
- 跨域消费者：[`account-suspension-and-appeal-lifecycle`](../../../user-identity-profile-relationship/settings-and-device-token/account-suspension-and-appeal-lifecycle/spec.md)。
- 父级设计：[L2 DEC-001](../design.md#dec-001)
- 测试证据：`local_contract` 证明领域不变量，`api_integration` 证明真实 PostgreSQL、HTTP 与 UserAccount public internal contract 边界，`user_acceptance` 必须由 `GWT-003` 的 Gamma Android/iOS 与受保护 Prod 演练提供。

## 7. 开放事项

<a id="open-001"></a>
### OPEN-001 Gamma 真实账号治理端到端证据

- 类型：`external_blocker`
- 优先级：`P0`
- 准出影响：`block`
- 影响或价值：尚缺 Gamma operator OIDC、细分 scope、服务身份、UserAccount Remote、双端设备、旧凭据拒绝、跨域 restriction 收敛及 telemetry/alert readback；仓内实现与真实存储集成测试不能替代这些证据。
- 完成判定：`GWT-003` 在 Gamma Android/iOS 与受保护账号上真实通过，CaseResult 绑定 decision/trace、UserAccount receipt、跨域 lag、DLQ/readiness 和告警 readback。

<a id="open-002"></a>
### OPEN-002 正式申诉 intake 与用户安全续接

- 类型：`external_blocker`
- 优先级：`P0`
- 准出影响：`block`
- 影响或价值：仓内已由 User 领域实现 identity-bound `AccountAppealIntake`，Product Ops production composition 也已使用最小 scope 的真实 User HTTP claim adapter，精确认领 `{intakeRef, accountId, caseId}`，不再使用 nil/fake verifier。该内部 claim 单轨不等于用户端申诉已商用：四环境不可变官方 Web release/HTTPS URL、生产 OTP material、客服 owner/SLA、真实 PostgreSQL API integration、Provider/Widget、Gamma Android/iOS UAT 与受保护 Prod receipt 仍缺失；`OpenAccountAppealCase` 仍不得暴露给用户，匿名公共表单或 suspended access token 也不得作为替代。
- 完成判定：[`account-suspension-and-appeal-lifecycle OPEN-004`](../../../user-identity-profile-relationship/settings-and-device-token/account-suspension-and-appeal-lifecycle/spec.md#open-004) 关闭；Product Ops 仅消费其 opaque `intakeRef`，App 与 Gamma Journey 只以真实 intake receipt 认定提交成功。
- 依赖：User 领域 canonical intake、四环境官方 HTTPS URL、隐私保留口径、客服 owner 与处置 SLA。

<a id="open-003"></a>
### OPEN-003 受保护 Prod 恢复与回滚演练

- 类型：`risk`
- 优先级：`P0`
- 准出影响：`block`
- 影响或价值：尚无受保护 Prod 账号证明双签、Suspend/Restore、terminal DLQ、同 decision replay、告警、审计导出和发布回滚在生产拓扑可用。
- 完成判定：按审批窗口完成受保护 Prod 演练，所有 SLO/告警/readiness/审计证据可追溯，且演练账号恢复、新旧凭据语义与发布回滚通过。
