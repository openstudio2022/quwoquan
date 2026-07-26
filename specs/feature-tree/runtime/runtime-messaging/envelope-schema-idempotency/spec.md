# L3 Story：信封 Schema 幂等 (`envelope-schema-idempotency`)

> 所属能力：[`runtime-messaging`](../spec.md)

> Journey / Scenario：[`JNY-001 / SCN-004`](../../../spec.md#scn-004)

> 设计归属：[L1 DEC-001](../../design.md#dec-001)

## 1. 用户价值

作为开发或维护异步任务的工程角色，
我希望使用统一任务信封、幂等键和重试语义发布与消费任务，
从而不同生产者和消费者之间获得一致、可诊断且可重放的异步结果。

## 2. 范围与非目标

### In Scope

- “信封 Schema 幂等”的输入、可观察主路径、失败语义以及与父能力的交接。

### Out of Scope

- 父能力中由其他 Story 独立拥有的行为、能力级架构决定和实现任务。

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 信封 Schema 幂等

- “信封 Schema 幂等”必须通过父能力公开契约交付可观察结果；失败时返回 canonical failure，不写入成功事实。

<a id="req-002"></a>
### REQ-002 与上层 runtime 契约一致，禁止服务内重复实现

- 与上层 runtime 契约一致，禁止服务内重复实现。

## 4. 契约引用

- 父能力公开契约：[`L2 spec`](../spec.md)。

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 信封 Schema 幂等

- GIVEN 开发、测试或运维角色具备有效身份，且父能力声明的输入与上游事实成立。
- WHEN 参与者执行“信封 Schema 幂等”对应的公开行为。
- THEN 通过父能力公开契约交付“信封 Schema 幂等”的可观察结果。
- AND 失败时返回 canonical failure，且不产生伪成功事实。

<a id="gwt-002"></a>
### GWT-002 生产、消费、重试与 dead letter 保持幂等

- GIVEN 生产者发布版本化任务，消费者遇到成功、重试或不可恢复失败。
- WHEN 消息被重复投递、重放或转入 dead letter。
- THEN 幂等键保证结果一致，并保留可诊断的重试与死信终态。

## 6. 依赖

- 前置要求：[`runtime-messaging`](../spec.md) 的范围、要求与 SIT。
- 下游结果：本 Story 声明的 GWT 可观察结果。
- 父级设计：[L1 DEC-001](../../design.md#dec-001)

## 7. 开放事项

<a id="open-001"></a>
### OPEN-001 信封 Schema 幂等主路径尚未形成直接测试证据

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`；目标：以版本化 envelope、幂等键、重试和 dead letter 交付异步消息。
- 完成判定：`GWT-001` 对应行为满足且真实测试 `spec_ref` 有效。

<a id="open-002"></a>
### OPEN-002 生产、消费、重试与 dead letter 保持幂等尚未形成直接测试证据

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`；目标：以版本化 envelope、幂等键、重试和 dead letter 交付异步消息。
- 完成判定：`GWT-002` 对应行为满足且真实测试 `spec_ref` 有效。
