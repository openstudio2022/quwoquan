# L2 Business Capability：请求上下文传播 (`request-context-propagation`)

> 所属领域：[`gateway-orchestrator-foundation`](../spec.md)
>
> 设计归属：[L1 DEC-001](../design.md#dec-001)

## 1. 能力目标

让同一请求的主体、客户端、requestId、traceId 与 causationId 在同步和异步边界保持一致且可审计

## 2. 范围与非目标

### In Scope

- 由本目录 Story 组合交付“request-context-propagation”的独立业务结果。

### Out of Scope

- 其他 L2 的事实所有权、metadata schema 与实现施工步骤。

## 3. Journey / Scenario 贡献

- 横切工程能力：不直接拥有 AppRoot Scenario；调用本能力的业务领域仍承担对应 Journey 的产品责任。
  - 本能力处理：让同一请求的主体、客户端、requestId、traceId 与 causationId 在同步和异步边界保持一致且可审计。
  - 本能力输出：可供业务领域组合的公开结果与明确失败终态。

## 4. Story



- [`async-causation-link`](./async-causation-link/spec.md)：把 requestId、traceId 与 causationId 传入异步事件和可靠任务，使跨进程因果链可追踪。
- [`client-context-propagation`](./client-context-propagation/spec.md)：请求头与 decoder context 必须消费 `runtime-codegen` 生成结果。
- [`request-trace-generation`](./request-trace-generation/spec.md)：在入口缺少有效追踪标识时生成 requestId 与 traceId，并在响应、日志和下游调用中保持一致。

## 5. 能力要求

<a id="req-001"></a>
### REQ-001 request context propagation 能力 SIT

- 本能力必须组合直属 Story 与公开契约，交付“让同一请求的主体、客户端、requestId、traceId 与 causationId 在同步和异步边界保持一致且可审计”所定义的业务结果；失败终态必须可区分且不得伪造成功。

## 6. 契约与依赖

- 上游能力：[`gateway-orchestrator-foundation`](../spec.md) 声明的领域入口。
- 下游能力：本目录直接 Story 及其公开结果。
- 一致性要求：遵循本层或父 L1 DEC 声明的一致性边界。

## 7. 集成验收

<a id="sit-001"></a>
### SIT-001 request context propagation 能力 SIT

- GIVEN 执行“request context propagation 能力”所需的身份、输入与上游事实均有效。
- WHEN 参与者发起“request context propagation 能力”对应动作。
- THEN 直属 Story 共同交付“让同一请求的主体、客户端、requestId、traceId 与 causationId 在同步和异步边界保持一致且可审计”，失败终态可区分且不产生伪成功事实。

## 8. 开放事项

<a id="open-001"></a>
### OPEN-001 request context propagation 能力 SIT

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`；目标：让同一请求的主体、客户端、requestId、traceId 与 causationId 在同步和异步边界保持一致且可审计。
- 完成判定：`SIT-001` 对应行为满足且真实测试 `spec_ref` 有效
