# L3 Story：真实流量训练晋升 (`real-traffic-training-promotion`)

> 所属能力：[`evaluation-and-flywheel`](../spec.md)

> Journey / Scenario：[`JNY-011 / SCN-026`](../../../spec.md#scn-026)

> 设计归属：[L2 DEC-001](../design.md#dec-001)

## 1. 用户价值

作为消费推荐的用户或策略运营者，
我希望模型晋升必须先通过离线 replay 和在线 AB 口径，
从而获得可解释且受治理的推荐结果。

## 2. 范围与非目标

### In Scope

- “真实流量训练晋升”的输入、可观察主路径、失败语义以及与父能力的交接。
- gamma/prod 行为样本、dataset、registry、evaluation report、reload 证据。
- 本 Story 不包含训练作业、模型注册、推理 reload 或深度模型实现。

### Out of Scope

- 父能力中由其他 Story 独立拥有的行为、能力级架构决定和实现任务。

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 真实流量训练晋升

- “真实流量训练晋升”必须通过父能力公开契约交付可观察结果；失败时返回 canonical failure，不写入成功事实。

<a id="req-002"></a>
### REQ-002 模型晋升必须先通过离线 replay 和在线 AB 口径

- 模型晋升必须先通过离线 replay 和在线 AB 口径。

## 4. 契约引用

- canonical：`specs/feature-tree/recommendation-platform/rec-model-training/spec.md`
- canonical：`specs/feature-tree/recommendation-platform/rec-model-service/spec.md`

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 真实流量训练晋升

- GIVEN 消费推荐的用户或策略运营者具备有效身份，且父能力声明的输入与上游事实成立。
- WHEN 参与者执行“真实流量训练晋升”对应的公开行为。
- THEN 通过父能力公开契约交付“真实流量训练晋升”的可观察结果。
- AND 失败时返回 canonical failure，且不产生伪成功事实。

## 6. 依赖

- 前置要求：[`evaluation-and-flywheel`](../spec.md) 的范围、要求与 SIT。
- 下游结果：本 Story 声明的 GWT 可观察结果。
- 父级设计：[L2 DEC-001](../design.md#dec-001)

## 7. 开放事项

<a id="open-001"></a>
### OPEN-001 真实流量训练晋升 验收证据

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺少能够证明“真实流量训练晋升”已满足当前规格的真实测试证据。
- 完成判定：`GWT-001` 对应行为满足且真实测试 `spec_ref` 有效。
