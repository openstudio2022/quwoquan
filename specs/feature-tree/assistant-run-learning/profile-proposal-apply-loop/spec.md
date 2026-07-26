# L2 Business Capability：资料提案应用闭环 (`profile-proposal-apply-loop`)

> 所属领域：[`assistant-run-learning`](../spec.md)
>
> 设计归属：[本层 design.md](./design.md)

## 1. 能力目标

通过用户身份画像领域公开的 `ProfileUpdateProposal` 聚合契约，交付助手来源提案从生成、确认/拒绝到应用落档的跨领域闭环。

## 2. 范围与非目标

### In Scope

- path-only confirm/apply/reject 命名意图与 actor-scoped idempotency receipt
- confirmed -> applying -> applied|expired 持久化检查点
- Persona proposalId 幂等应用与并发 Reject 阻断
- 助手只提交 typed change、来源证据和理由；提案状态、receipt、outbox、应用审计与回滚由 user-service 聚合拥有

### Out of Scope

- 通用 Saga/工作流引擎
- 在 assistant-service 复制 `ProfileUpdateProposal` 状态机、数据库表或应用审计

## 3. Journey / Scenario 贡献

- [`JNY-007 / SCN-015`](../../spec.md#scn-015)
  - 本能力接收：该 Scenario 进入本能力边界的已授权主体与 canonical 输入。
  - 本能力处理：定义画像提案从生成、确认/拒绝到应用落档的完整闭环。
  - 本能力输出：直属 Story 组合产生的可观察结果与明确失败终态。
  - 失败时终态：保留已确认事实，并返回可恢复的 canonical failure。

## 4. Story



- [`proposal-apply-audit`](./proposal-apply-audit/spec.md)：定义“提案应用审计”的可观察主路径、失败语义及父能力交接。
- [`proposal-confirm-reject`](./proposal-confirm-reject/spec.md)：定义“提案确认拒绝”的可观察主路径、失败语义及父能力交接。
- [`proposal-create-review`](./proposal-create-review/spec.md)：定义“提案创建审核”的可观察主路径、失败语义及父能力交接。

## 5. 能力要求

<a id="req-001"></a>
### REQ-001 profile proposal apply loop 能力 SIT

- 调用方不提交 proposal version，纯 Proposal CAS 冲突由服务端重载重放。
- 已确认/已应用/已拒绝状态上的首次 no-op key 会持久化 receipt，后续状态演进后仍重放原始结果。
- applying 检查点先于 Persona 写入提交，并阻断并发 Reject。
- Persona 写入按 proposalId 幂等；响应丢失或进程重启后可从 applying 续作。
- 目标 Persona 快照失效时进入 expired，不产生 Proposal rejected 但 Persona 已应用。

<a id="req-002"></a>
### REQ-002 提案状态流转必须强一致并具备幂等控制

- 提案状态流转必须强一致并具备幂等控制。
- 所有提案操作必须产生日志审计与追踪标识。

## 6. 契约与依赖

- 上游能力：[`assistant-run-learning`](../spec.md) 声明的领域入口。
- 下游能力：本目录直接 Story 及其公开结果。
- 一致性要求：遵循本层或父 L1 DEC 声明的一致性边界。

## 7. 集成验收

<a id="sit-001"></a>
### SIT-001 profile proposal apply loop 能力 SIT

- GIVEN 执行“profile proposal apply loop 能力”所需的身份、输入与上游事实均有效。
- WHEN 参与者发起“profile proposal apply loop 能力”对应动作。
- THEN 调用方不提交 proposal version，纯 Proposal CAS 冲突由服务端重载重放。
- THEN 已确认/已应用/已拒绝状态上的首次 no-op key 会持久化 receipt，后续状态演进后仍重放原始结果。
- THEN applying 检查点先于 Persona 写入提交，并阻断并发 Reject。
- THEN Persona 写入按 proposalId 幂等；响应丢失或进程重启后可从 applying 续作。
- THEN 目标 Persona 快照失效时进入 expired，不产生 Proposal rejected 但 Persona 已应用。
