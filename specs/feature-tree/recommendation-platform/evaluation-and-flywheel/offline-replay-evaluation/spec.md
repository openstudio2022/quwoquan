# L3 Story：离线回放评估 (`offline-replay-evaluation`)

> 所属能力：[`evaluation-and-flywheel`](../spec.md)

> Journey / Scenario：[`JNY-011 / SCN-026`](../../../spec.md#scn-026)

> 设计归属：[L2 DEC-001](../design.md#dec-001)

## 1. 用户价值

作为消费推荐的用户或策略运营者，
我希望低于门槛的策略不得进入线上 AB，
从而获得可解释且受治理的推荐结果。

## 2. 范围与非目标

### In Scope

- “离线回放评估”的输入、可观察主路径、失败语义以及与父能力的交接。
- replay 数据集、NDCG/Recall@K/MAP/覆盖率/多样性/校准误差、协同召回 lift 和 fact/affinity 解释 CTR。
- 批量调度、数据仓库 ETL 或深排训练 replay 平台。

### Out of Scope

- 父能力中由其他 Story 独立拥有的行为、能力级架构决定和实现任务。

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 离线回放评估

- “离线回放评估”必须通过父能力公开契约交付可观察结果；失败时返回 canonical failure，不写入成功事实。

<a id="req-002"></a>
### REQ-002 低于门槛的策略不得进入线上 AB

- 低于门槛的策略不得进入线上 AB。

## 4. 契约引用

- canonical：`quwoquan_service/services/content-service/observability/slo/recommendation_slo.yaml`

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 离线回放评估

- GIVEN 消费推荐的用户或策略运营者具备有效身份，且父能力声明的输入与上游事实成立。
- WHEN 参与者执行“离线回放评估”对应的公开行为。
- THEN 通过父能力公开契约交付“离线回放评估”的可观察结果。
- AND 失败时返回 canonical failure，且不产生伪成功事实。

## 6. 依赖

- 前置要求：[`evaluation-and-flywheel`](../spec.md) 的范围、要求与 SIT。
- 下游结果：本 Story 声明的 GWT 可观察结果。
- 父级设计：[L2 DEC-001](../design.md#dec-001)
