# L2 Design：资料提案应用闭环 (`profile-proposal-apply-loop`)

> 对应规格：[L2 spec](./spec.md)

> 设计触发原因：“定义画像提案从生成、确认/拒绝到应用落档的完整闭环”需要 `proposal-apply-audit`、`proposal-confirm-reject`、`proposal-create-review` 共享状态 owner、契约或质量边界。

## 1. 背景、目标与非目标

- 设计目标：定义画像提案从生成、确认/拒绝到应用落档的完整闭环。
- 非目标：复制字段 schema、实现任务、测试排列组合或执行历史。

## 2. Story 协作与状态流

- [`proposal-apply-audit`](./proposal-apply-audit/spec.md)：定义“提案应用审计”的可观察主路径、失败语义及父能力交接。
- [`proposal-confirm-reject`](./proposal-confirm-reject/spec.md)：定义“提案确认拒绝”的可观察主路径、失败语义及父能力交接。
- [`proposal-create-review`](./proposal-create-review/spec.md)：定义“提案创建审核”的可观察主路径、失败语义及父能力交接。

## 3. 端云与数据流

- 上游能力：[`assistant-run-learning`](../spec.md) 声明的领域入口。
- authoritative owner：`ProfileUpdateProposal`、Persona 变更、command receipt、outbox、apply audit 与 rollback record 只由 user-service 的用户身份画像领域拥有。
- assistant boundary：assistant-service 只产生 typed change、来源证据与理由，并通过 user-service 公开 command 提交；不得直连其 Postgres、导入其 internal/generated 实现或维护影子状态。
- 下游能力：本目录直接 Story 及 user-service 公开聚合结果。
- 一致性要求：遵循本层或父 L1 DEC 声明的一致性边界。

## 4. 关键决策

<a id="dec-001"></a>
### DEC-001 用户确认后才允许应用画像提案
- 决策：用户确认后才允许应用画像提案。
- 理由：定义画像提案从生成、确认/拒绝到应用落档的完整闭环。
- 被否决方案：由 assistant-service、调用方、页面或脚本复制 user-service 聚合状态并绕过公开契约。
- 约束与影响：所有状态迁移、幂等 receipt、Persona 应用、审计和回滚都在 user-service 聚合边界内完成；助手与 App 只消费生成的公开 contract。
- 关联要求：`REQ-001`
- 影响 Story：[`proposal-apply-audit`](./proposal-apply-audit/spec.md)、[`proposal-confirm-reject`](./proposal-confirm-reject/spec.md)、[`proposal-create-review`](./proposal-create-review/spec.md)
- 关联验收：`SIT-001`

## 5. 失败与恢复

- 失败类型：权限拒绝、依赖超时、版本冲突或持久化失败。
- 可见结果：调用方收到可区分的 canonical failure 或规格明确允许的降级结果；任何失败均不写入成功事实。
- 恢复动作：调用方按 canonical recovery action 重试、刷新或停止；不得自行合成成功结果。
- 禁止 fallback：不得回退到 Mock、旧 wire、双读双写或页面本地写副本。

## 6. 质量与观测

- 沿用父 L1 质量约束；新增特有 SLO 时在本节声明。
