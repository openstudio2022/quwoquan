# L3 Story：助手对象运行与授权门控 (`assistant-object-runtime`)

> 所属能力：[助手运行基座](../spec.md)
>
> Journey / Scenario：[`JNY-009 / SCN-017`](../../../spec.md#scn-017)
>
> 设计归属：[L2 DEC-001](../design.md#dec-001)

## 1. 用户价值

作为使用小趣助理的用户，我希望会话、运行与订阅在服务重启后仍可继续，并在敏感能力执行前校验授权，从而获得连续且可控制的助理体验。

## 2. 范围与非目标

### In Scope

- 持久化 AssistantConversation、AssistantRun/Turn、SkillSubscription 与 SkillConsent 的 owner 状态。
- 创建命令幂等、运行终态互斥、主动投递 lease 和 consent fail-closed。

### Out of Scope

- 模型选择、内容事实和端侧页面视觉设计。

## 3. 行为要求

### REQ-001 持久化运行与授权

- 服务重启后必须能按 owner 读取会话与运行；敏感操作在 consent 缺失、撤销或存储不可用时必须拒绝执行。
- 同一 intent 的重复创建不得产生第二个运行；completed、failed、cancelled 终态不得互相迁移。

## 4. 契约引用

- operation：`quwoquan_service/services/assistant-service/contracts/assistant/assistant_run/operations.yaml`
- consent：`quwoquan_service/services/assistant-service/contracts/assistant/skill_consent/operations.yaml`

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 重启恢复与授权拒绝

- GIVEN 已持久化的会话包含运行记录，且另一个敏感操作没有有效 consent。
- WHEN assistant-service 重启后读取运行并尝试执行敏感操作。
- THEN 原运行仍通过 metadata-owned `AssistantTurnEnvelope` 可读取；即使有限保留期的 SSE journal 已过期，completed 的 `answerText`，或 failed/cancelled 的 canonical terminal failure，以及状态、trace 与恢复状态仍来自 Run Store 的 canonical snapshot。
- AND 敏感操作返回 canonical 授权失败，且不产生工具调用或成功事实。

## 6. 依赖

- 前置要求：父能力的对象 Store、lease 与 typed Facet 边界。
- 上游事实：登录主体、Persona 与 consent。
- 下游结果：可续接的运行或明确授权失败。
- 父级设计：`DEC-001`
