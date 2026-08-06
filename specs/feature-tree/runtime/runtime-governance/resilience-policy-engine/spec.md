# L3 Story：韧性策略引擎 (`resilience-policy-engine`)

> 所属能力：[`runtime-governance`](../spec.md)

> Journey / Scenario：[`JNY-001 / SCN-004`](../../../spec.md#scn-004)

> 设计归属：[L1 DEC-001](../../design.md#dec-001)

## 1. 用户价值

作为维护服务可靠性的工程角色，
我希望统一执行出站熔断与 owner 侧并发背压，并按 operation 准入放行或摘除负载，
从而在依赖失败时获得可解释且不会放大故障的恢复结果。

## 2. 范围与非目标

### In Scope

- “韧性策略引擎”的输入、可观察主路径、失败语义以及与父能力的交接。

### Out of Scope

- 父能力中由其他 Story 独立拥有的行为、能力级架构决定和实现任务。

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 韧性策略引擎

- “韧性策略引擎”必须通过父能力公开契约交付可观察结果；失败时返回 canonical failure，不写入成功事实。

<a id="req-002"></a>
### REQ-002 与上层 runtime 契约一致，禁止服务内重复实现

- 与上层 runtime 契约一致，禁止服务内重复实现。

<a id="req-003"></a>
### REQ-003 本 Story 不拥有入站超时真相源，已删除的策略骨架不得回归

- 入站单 operation 超时预算的唯一真相源是 operation 契约的 `reliability.timeout_ms`，经生成的入口安全描述符在 guard 层以 `context.WithTimeout` 强制；本 Story 既不持有该数值，也不复制或覆盖它。
- 韧性策略结构体、策略提供者接口、静态策略提供者与重试策略，连同编排层下游超时配置键，已作为零生产调用方的骨架删除。本 Story 因此**不提供任何重试能力**；实现、门禁与规格均不得重新引入它们，也不得把它们当作超时或重试的真相源。
- 熔断器、客户端熔断包装、并发背压限流器、operation 准入中间件与 feature flag 判定是本 Story 当前真实在用的治理装置，不随上述骨架一并退役。
- 本 Story 不提供速率限流器：业务到达速率配额由 api-edge 共享状态在 owner 之前独占执行。

## 4. 契约引用

- 父能力公开契约：[`L2 spec`](../spec.md)。

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 韧性策略引擎

- GIVEN 开发、测试或运维角色具备有效身份，且父能力声明的输入与上游事实成立。
- WHEN 参与者执行“韧性策略引擎”对应的公开行为。
- THEN 通过父能力公开契约交付“韧性策略引擎”的可观察结果。
- AND 失败时返回 canonical failure，且不产生伪成功事实。

<a id="gwt-002"></a>
### GWT-002 熔断与并发背压状态可观察

- GIVEN 服务调用命中出站熔断、owner 侧并发背压或 operation 准入。
- WHEN 治理装置作出允许、拒绝或负载摘除决定。
- THEN 调用结果不放大故障，且治理状态与剩余恢复条件可观察。

## 6. 依赖

- 前置要求：[`runtime-governance`](../spec.md) 的范围、要求与 SIT。
- 下游结果：本 Story 声明的 GWT 可观察结果。
- 父级设计：[L1 DEC-001](../../design.md#dec-001)

## 7. 开放事项

<a id="open-001"></a>
### OPEN-001 韧性策略引擎主路径尚未形成直接测试证据

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`；目标：为服务调用执行出站熔断、owner 侧并发背压与 feature flag 判定，并暴露可观测治理状态。
- 完成判定：`GWT-001` 对应行为满足且真实测试 `spec_ref` 有效。

<a id="open-002"></a>
### OPEN-002 熔断与并发背压状态可观察尚未形成完整测试证据

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：仍缺出站熔断状态迁移与剩余恢复条件的直接 `spec_ref`；目标：出站熔断、owner 侧并发背压与 operation 准入的允许、拒绝和负载摘除决定可观察。operation 准入的 `inflight_full` 拒绝已由 `quwoquan_service/tests/local_contract/runtime/governance/operation_admission__local_contract_test.go` 覆盖。
- 完成判定：`GWT-002` 对应行为满足且真实测试 `spec_ref` 有效。
