# L2 Business Capability：编排降级回滚 (`orchestration-degradation-rollback`)

> 所属领域：[`gateway-orchestrator-foundation`](../spec.md)
>
> 设计归属：[L1 DEC-001](../design.md#dec-001)

## 1. 能力目标

在聚合调用、下游超时或路由变更失败时维持稳定响应契约，并通过显式降级和可审计回滚恢复服务

## 2. 范围与非目标

### In Scope

- 由本目录 Story 组合交付“orchestration-degradation-rollback”的独立业务结果。

### Out of Scope

- 其他 L2 的事实所有权、metadata schema 与实现施工步骤。

## 3. Journey / Scenario 贡献

- 横切工程能力：不直接拥有 AppRoot Scenario；调用本能力的业务领域仍承担对应 Journey 的产品责任。
  - 本能力处理：在聚合调用、下游超时或路由变更失败时维持稳定响应契约，并通过显式降级和可审计回滚恢复服务。
  - 本能力输出：可供业务领域组合的公开结果与明确失败终态。

## 4. Story



- [`aggregation-contract-stability`](./aggregation-contract-stability/spec.md)：聚合多个下游结果时保持公开响应结构稳定，并将局部失败映射为 canonical failure 或显式降级。
- [`downstream-timeout-fallback`](./downstream-timeout-fallback/spec.md)：下游超时时遵守调用预算并返回预先声明的降级结果，禁止无限等待或伪造完整成功。
- [`rollback-playbook`](./rollback-playbook/spec.md)：网关配置或路由变更触发错误预算时回退上一份已验证 revision，并保留可审计结果。

## 5. 能力要求

<a id="req-001"></a>
### REQ-001 编排降级回滚能力组合结果

- 本能力必须组合直属 Story 与公开契约，交付“在聚合调用、下游超时或路由变更失败时维持稳定响应契约，并通过显式降级和可审计回滚恢复服务”所定义的业务结果；失败终态必须可区分且不得伪造成功。

## 6. 契约与依赖

- 上游能力：[`gateway-orchestrator-foundation`](../spec.md) 声明的领域入口。
- 下游能力：本目录直接 Story 及其公开结果。
- 一致性要求：遵循本层或父 L1 DEC 声明的一致性边界。

## 7. 集成验收

<a id="sit-001"></a>
### SIT-001 orchestration degradation rollback 能力 SIT

- GIVEN 执行“orchestration degradation rollback 能力”所需的身份、输入与上游事实均有效。
- WHEN 参与者发起“orchestration degradation rollback 能力”对应动作。
- THEN 直属 Story 共同交付“在聚合调用、下游超时或路由变更失败时维持稳定响应契约，并通过显式降级和可审计回滚恢复服务”，失败终态可区分且不产生伪成功事实。

## 8. 开放事项

<a id="open-001"></a>
### OPEN-001 orchestration degradation rollback 能力 SIT

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`；目标：在聚合调用、下游超时或路由变更失败时维持稳定响应契约，并通过显式降级和可审计回滚恢复服务。
- 完成判定：`SIT-001` 对应行为满足且真实测试 `spec_ref` 有效
