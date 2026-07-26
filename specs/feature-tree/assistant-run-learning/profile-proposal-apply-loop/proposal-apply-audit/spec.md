# L3 Story：提案应用审计 (`proposal-apply-audit`)

> 所属能力：[`profile-proposal-apply-loop`](../spec.md)

> Journey / Scenario：[`JNY-007 / SCN-015`](../../../spec.md#scn-015)

> 设计归属：[L2 DEC-001](../design.md#dec-001)

## 1. 用户价值

作为使用小趣的用户或助手运营者，
我希望应用动作必须记录前后快照与操作者上下文，
从而获得可解释、可恢复且可持续改进的助手结果。

## 2. 范围与非目标

### In Scope

- “提案应用审计”的输入、可观察主路径、失败语义以及与父能力的交接。

### Out of Scope

- 父能力中由其他 Story 独立拥有的行为、能力级架构决定和实现任务。

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 提案应用审计

- “提案应用审计”必须通过父能力公开契约交付可观察结果；失败时返回 canonical failure，不写入成功事实。

<a id="req-002"></a>
### REQ-002 应用动作必须记录前后快照与操作者上下文

- 应用动作必须记录前后快照与操作者上下文。

<a id="req-003"></a>
### REQ-003 应用操作必须支持回滚，并保留前后版本差异记录

- 应用操作必须支持回滚，并保留前后版本差异记录。

## 4. 契约引用

- 父能力公开契约：[`L2 spec`](../spec.md)。

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 提案应用审计

- GIVEN owner 已确认提案，目标 Persona 版本与提案快照一致，且 apply command 携带稳定幂等身份。
- WHEN user-service 聚合应用提案或在允许窗口内回滚一次已应用提案。
- THEN Persona 变更、pre/post snapshot、actor/trace、target version、receipt 与 immutable audit record 具有一致的可观察终态。
- AND 响应丢失重试返回同一 receipt；版本冲突、越权或过期回滚返回 canonical failure，不留下半应用或无审计成功事实。

## 6. 依赖

- 前置要求：[`profile-proposal-apply-loop`](../spec.md) 的范围、要求与 SIT。
- 下游结果：本 Story 声明的 GWT 可观察结果。
- 父级设计：[L2 DEC-001](../design.md#dec-001)
