# L3 Story：推荐可观测性看板 (`recommendation-observability-dashboard`)

> 所属能力：[`evaluation-and-flywheel`](../spec.md)

> Journey / Scenario：[`JNY-011 / SCN-026`](../../../spec.md#scn-026)

> 设计归属：[L2 DEC-001](../design.md#dec-001)

## 1. 用户价值

作为消费推荐的用户或策略运营者，
我希望所有核心分桶标签均来自 bounded attribution 契约，禁止引入高基数自由文本标签，
从而获得可解释且受治理的推荐结果。

## 2. 范围与非目标

### In Scope

- “推荐可观测性看板”的输入、可观察主路径、失败语义以及与父能力的交接。
- 推荐 served 与 behavior 归因指标看板。
- 首页、旅行、精品、UGC、数据工程供给、召回路径、交集类别和 reason version 分桶。
- unknown attribution rate、CTR、负反馈率、served 分布和供给占比。
- 深排平台、双塔 ANN、MMoE/PLE/ESMM、IPS/Thompson 或同步 scorer。
- 离线 replay 脚本、在线 AB 平台或真实流量训练晋升。

### Out of Scope

- 父能力中由其他 Story 独立拥有的行为、能力级架构决定和实现任务。

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 推荐可观测性看板

- “推荐可观测性看板”必须通过父能力公开契约交付可观察结果；失败时返回 canonical failure，不写入成功事实。

<a id="req-002"></a>
### REQ-002 所有核心分桶标签均来自 bounded attribution 契约，禁止引入高基数自由文本标签

- 所有核心分桶标签均来自 bounded attribution 契约，禁止引入高基数自由文本标签。

## 4. 契约引用

- canonical：`quwoquan_ops/observability/monitoring/dashboards/l2_recommendation_commercial_maturity.json`
- canonical：`quwoquan_service/services/content-service/observability/slo/recommendation_slo.yaml`

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 推荐可观测性看板

- GIVEN 消费推荐的用户或策略运营者具备有效身份，且父能力声明的输入与上游事实成立。
- WHEN 参与者执行“推荐可观测性看板”对应的公开行为。
- THEN 通过父能力公开契约交付“推荐可观测性看板”的可观察结果。
- AND 失败时返回 canonical failure，且不产生伪成功事实。

## 6. 依赖

- 前置要求：[`evaluation-and-flywheel`](../spec.md) 的范围、要求与 SIT。
- 下游结果：本 Story 声明的 GWT 可观察结果。
- 父级设计：[L2 DEC-001](../design.md#dec-001)
