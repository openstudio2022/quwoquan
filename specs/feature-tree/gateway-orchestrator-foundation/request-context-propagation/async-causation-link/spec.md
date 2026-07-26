# L3 Story：异步因果链路 (`async-causation-link`)

> 所属能力：[`request-context-propagation`](../spec.md)

> Journey / Scenario：横切工程能力；由父 L2 spec 参与 AppRoot Journey。

> 设计归属：[L1 DEC-001](../../design.md#dec-001)

## 1. 用户价值

作为调用应用服务的客户端或平台服务，
我希望把 requestId、traceId 与 causationId 传入异步事件和可靠任务，使跨进程因果链可追踪，
从而获得安全、可追踪且可降级的统一入口。

## 2. 范围与非目标

### In Scope

- “异步因果链路”的输入、可观察主路径、失败语义以及与父能力的交接。

### Out of Scope

- 父能力中由其他 Story 独立拥有的行为、能力级架构决定和实现任务。

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 异步因果链路

- 把 requestId、traceId 与 causationId 传入异步事件和可靠任务，使跨进程因果链可追踪。

## 4. 契约引用

- 父能力公开契约：[`L2 spec`](../spec.md)。

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 异步因果链路

- GIVEN 调用应用服务的客户端或平台服务具备有效身份，且父能力声明的输入与上游事实成立。
- WHEN 参与者执行“异步因果链路”对应的公开行为。
- THEN 把 requestId、traceId 与 causationId 传入异步事件和可靠任务，使跨进程因果链可追踪。
- AND 失败时返回 canonical failure，且不产生伪成功事实。

## 6. 依赖

- 前置要求：[`request-context-propagation`](../spec.md) 的范围、要求与 SIT。
- 下游结果：本 Story 声明的 GWT 可观察结果。
- 父级设计：[L1 DEC-001](../../design.md#dec-001)

## 7. 开放事项

<a id="open-001"></a>
### OPEN-001 异步因果链路 验收证据

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺少能够证明“异步因果链路”已满足当前规格的真实测试证据。
- 完成判定：`GWT-001` 对应行为满足且真实测试 `spec_ref` 有效。
