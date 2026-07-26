# L3 Story：下游超时与显式降级 (`downstream-timeout-fallback`)

> 所属能力：[`orchestration-degradation-rollback`](../spec.md)

> Journey / Scenario：横切工程能力；由父 L2 spec 参与 AppRoot Journey。

> 设计归属：[L1 DEC-001](../../design.md#dec-001)

## 1. 用户价值

作为调用应用服务的客户端或平台服务，
我希望下游超时时遵守调用预算并返回预先声明的降级结果，禁止无限等待或伪造完整成功，
从而获得安全、可追踪且可降级的统一入口。

## 2. 范围与非目标

### In Scope

- “下游超时与显式降级”的输入、可观察主路径、失败语义以及与父能力的交接。

### Out of Scope

- 父能力中由其他 Story 独立拥有的行为、能力级架构决定和实现任务。

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 下游超时与显式降级

- 下游超时时遵守调用预算并返回预先声明的降级结果，禁止无限等待或伪造完整成功。

## 4. 契约引用

- 父能力公开契约：[`L2 spec`](../spec.md)。

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 下游超时与显式降级

- GIVEN 调用应用服务的客户端或平台服务具备有效身份，且父能力声明的输入与上游事实成立。
- WHEN 参与者执行“下游超时与显式降级”对应的公开行为。
- THEN 下游超时时遵守调用预算并返回预先声明的降级结果，禁止无限等待或伪造完整成功。
- AND 失败时返回 canonical failure，且不产生伪成功事实。

## 6. 依赖

- 前置要求：[`orchestration-degradation-rollback`](../spec.md) 的范围、要求与 SIT。
- 下游结果：本 Story 声明的 GWT 可观察结果。
- 父级设计：[L1 DEC-001](../../design.md#dec-001)

## 7. 开放事项

<a id="open-001"></a>
### OPEN-001 下游超时与显式降级 验收证据

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺少能够证明“下游超时与显式降级”已满足当前规格的真实测试证据。
- 完成判定：`GWT-001` 对应行为满足且真实测试 `spec_ref` 有效。
