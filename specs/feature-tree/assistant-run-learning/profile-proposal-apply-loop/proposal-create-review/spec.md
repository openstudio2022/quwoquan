# L3 Story：提案创建审核 (`proposal-create-review`)

> 所属能力：[`profile-proposal-apply-loop`](../spec.md)

> Journey / Scenario：[`JNY-007 / SCN-015`](../../../spec.md#scn-015)

> 设计归属：[L2 DEC-001](../design.md#dec-001)

## 1. 用户价值

作为使用小趣的用户或助手运营者，
我希望提案内容必须具备来源与理由字段，便于审计与解释，
从而获得可解释、可恢复且可持续改进的助手结果。

## 2. 范围与非目标

### In Scope

- “提案创建审核”的输入、可观察主路径、失败语义以及与父能力的交接。

### Out of Scope

- 父能力中由其他 Story 独立拥有的行为、能力级架构决定和实现任务。

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 提案创建审核

- “提案创建审核”必须通过父能力公开契约交付可观察结果；失败时返回 canonical failure，不写入成功事实。

<a id="req-002"></a>
### REQ-002 提案内容必须具备来源与理由字段，便于审计与解释

- 提案内容必须具备来源与理由字段，便于审计与解释。

<a id="req-003"></a>
### REQ-003 提案必须包含变更理由、来源证据与影响范围

- 提案必须包含变更理由、来源证据与影响范围。

## 4. 契约引用

- 父能力公开契约：[`L2 spec`](../spec.md)。

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 提案创建审核

- GIVEN Persona owner 或获授权的助手来源提交 typed change、变更理由、来源证据、影响范围与稳定 clientRequestId。
- WHEN user-service 的 `ProfileUpdateProposal` 公开 command 创建提案。
- THEN 返回 owner-scoped pending 提案及可审核的来源、理由和影响范围，同一 intent 重试返回同一 receipt。
- AND 非 owner、非法 change/evidence 或幂等冲突返回 canonical failure，且 assistant-service、App 和页面均不创建影子提案或伪成功状态。

## 6. 依赖

- 前置要求：[`profile-proposal-apply-loop`](../spec.md) 的范围、要求与 SIT。
- 下游结果：本 Story 声明的 GWT 可观察结果。
- 父级设计：[L2 DEC-001](../design.md#dec-001)
