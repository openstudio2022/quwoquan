# L3 Story：分桶策略引擎 (`bucketing-strategy-engine`)

> 所属能力：[`experiment-bucketing-and-rollout`](../spec.md)

> Journey / Scenario：[`JNY-002 / SCN-005`](../../../spec.md#scn-005)

> 设计归属：[L1 DEC-001](../../design.md#dec-001)

## 1. 用户价值

作为产品运营或增长角色，
我希望以服务端稳定主体键、experimentId 和受控 salt 计算唯一分桶并写入曝光事实，
从而获得可度量、可回滚的运营结果。

## 2. 范围与非目标

### In Scope

- “分桶策略引擎”的输入、可观察主路径、失败语义以及与父能力的交接。

### Out of Scope

- 父能力中由其他 Story 独立拥有的行为、能力级架构决定和实现任务。

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 分桶策略引擎

- 以服务端稳定主体键、experimentId 和受控 salt 计算唯一分桶并写入曝光事实。

## 4. 契约引用

- 父能力公开契约：[`L2 spec`](../spec.md)。

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 分桶策略引擎

- GIVEN 产品运营或增长角色具备有效身份，且父能力声明的输入与上游事实成立。
- WHEN 参与者执行“分桶策略引擎”对应的公开行为。
- THEN 以服务端稳定主体键、experimentId 和受控 salt 计算唯一分桶并写入曝光事实。
- AND 失败时返回 canonical failure，且不产生伪成功事实。

## 6. 依赖

- 前置要求：[`experiment-bucketing-and-rollout`](../spec.md) 的范围、要求与 SIT。
- 下游结果：本 Story 声明的 GWT 可观察结果。
- 父级设计：[L1 DEC-001](../../design.md#dec-001)

## 7. 开放事项

<a id="open-001"></a>
### OPEN-001 分桶策略引擎 验收证据

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺少能够证明“分桶策略引擎”已满足当前规格的真实测试证据。
- 完成判定：`GWT-001` 对应行为满足且真实测试 `spec_ref` 有效。
