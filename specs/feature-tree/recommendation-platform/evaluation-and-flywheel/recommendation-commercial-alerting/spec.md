# L3 Story：推荐商用告警 (`recommendation-commercial-alerting`)

> 所属能力：[`evaluation-and-flywheel`](../spec.md)

> Journey / Scenario：[`JNY-011 / SCN-026`](../../../spec.md#scn-026)

> 设计归属：[L2 DEC-001](../design.md#dec-001)

## 1. 用户价值

作为消费推荐的用户或策略运营者，
我希望告警表达式不得引用 `recommendation_offline_eval_metric_value`、`eligible_feed_item_count`、`collaborative_recall_lift` 等 objective_only 口径，
从而获得可解释且受治理的推荐结果。

## 2. 范围与非目标

### In Scope

- “推荐商用告警”的输入、可观察主路径、失败语义以及与父能力的交接。
- unknown attribution rate 告警。
- 负反馈率按 supply_source/channel/vertical 分桶告警。
- CTR 按 recall_path/channel/vertical 分桶告警。
- 旅行与精品场景消费率告警。
- UGC 与数据工程供给 share 失衡告警。

### Out of Scope

- 父能力中由其他 Story 独立拥有的行为、能力级架构决定和实现任务。

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 推荐商用告警

- 告警表达式不得引用 `recommendation_offline_eval_metric_value`、`eligible_feed_item_count`、`collaborative_recall_lift` 等 objective_only 口径。

<a id="req-002"></a>
### REQ-002 告警表达式不得引用 recommendation_offline_eval_metric_value、eligible_feed_item_count、collaborative_recall_lift 等 objective_only 口径

- 告警表达式不得引用 `recommendation_offline_eval_metric_value`、`eligible_feed_item_count`、`collaborative_recall_lift` 等 objective_only 口径。

## 4. 契约引用

- canonical：`quwoquan_service/services/content-service/observability/slo/recommendation_slo.yaml`
- canonical：`quwoquan_ops/observability/monitoring/alerts/quwoquan_alerts.yaml`

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 推荐商用告警

- GIVEN 消费推荐的用户或策略运营者具备有效身份，且父能力声明的输入与上游事实成立。
- WHEN 参与者执行“推荐商用告警”对应的公开行为。
- THEN 告警表达式不得引用 `recommendation_offline_eval_metric_value`、`eligible_feed_item_count`、`collaborative_recall_lift` 等 objective_only 口径。
- AND 失败时返回 canonical failure，且不产生伪成功事实。

## 6. 依赖

- 前置要求：[`evaluation-and-flywheel`](../spec.md) 的范围、要求与 SIT。
- 下游结果：本 Story 声明的 GWT 可观察结果。
- 父级设计：[L2 DEC-001](../design.md#dec-001)
