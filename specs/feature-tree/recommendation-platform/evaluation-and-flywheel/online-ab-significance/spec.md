# L3 Story：在线 A/B 显著性 (`online-ab-significance`)

> 所属能力：[`evaluation-and-flywheel`](../spec.md)

> Journey / Scenario：[`JNY-011 / SCN-026`](../../../spec.md#scn-026)

> 设计归属：[L2 DEC-001](../design.md#dec-001)

## 1. 用户价值

作为消费推荐的用户或策略运营者，
我希望以稳定分桶、样本量和显著性阈值评估线上策略，样本不足时保持 hold，
从而获得可解释且受治理的推荐结果。

## 2. 范围与非目标

### In Scope

- “在线 A/B 显著性”的输入、可观察主路径、失败语义以及与父能力的交接。
- champion/challenger、分桶标签、样本量、SRM、显著性、relative lift、晋级/回滚结论和护栏指标。
- 本 Story 不包含 AB 框架或线上流量切分实现。

### Out of Scope

- 父能力中由其他 Story 独立拥有的行为、能力级架构决定和实现任务。

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 在线 A/B 显著性

- 以稳定分桶、样本量和显著性阈值评估线上策略，样本不足时保持 hold。

## 4. 契约引用

- canonical：`quwoquan_service/services/content-service/observability/slo/recommendation_slo.yaml`

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 在线 A/B 显著性

- GIVEN 消费推荐的用户或策略运营者具备有效身份，且父能力声明的输入与上游事实成立。
- WHEN 参与者执行“在线 A/B 显著性”对应的公开行为。
- THEN 以稳定分桶、样本量和显著性阈值评估线上策略，样本不足时保持 hold。
- AND 失败时返回 canonical failure，且不产生伪成功事实。

## 6. 依赖

- 前置要求：[`evaluation-and-flywheel`](../spec.md) 的范围、要求与 SIT。
- 下游结果：本 Story 声明的 GWT 可观察结果。
- 父级设计：[L2 DEC-001](../design.md#dec-001)
