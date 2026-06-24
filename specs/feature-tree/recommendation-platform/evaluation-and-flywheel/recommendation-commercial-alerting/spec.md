# L3 Story：recommendation-commercial-alerting

## 功能说明

`recommendation-commercial-alerting` 是非深排推荐商用成熟度 P1a 的告警层。它承接 P0+ bounded attribution 指标和 P1 商用看板，把“看得到问题”推进到“问题持续出现时必须响应”，覆盖端云归因丢失、分场景消费断崖、供给来源失衡、召回路径 CTR 异常和负反馈异常。

## 范围

- 推荐商用归因告警：`unknown attribution`、`negative feedback by supply_source`、`CTR by recall_path`、`travel/premium consumption`、`UGC/data_engineering supply share`。
- 告警只引用 P0+ 真实 emitter：`recommendation_feed_served_by_attribution_total`、`recommendation_behavior_by_attribution_total`。
- 告警分桶只使用 bounded labels：`channel`、`vertical`、`supply_source`、`recall_path`、`ranking_version`、`reason_version`、`intersection_class`。
- SLO、Prometheus 规则、local_contract 测试和 CR 同步更新。

## 非目标

- 不实现深排平台、双塔 ANN、MMoE/PLE/ESMM、IPS/Thompson 或同步 scorer。
- 不实现离线 replay、在线 AB 显著性、真实流量训练晋升或策略自动晋升。
- 不实现 product-ops 全局精品池写入、审计、过期、回滚和下架实时剔除。
- 不把低流量分桶告警结果作为 AB 显著性结论。

## 验收标准

- A1：所有 P1a 商用告警均绑定 `recommendation_slo.yaml` 中的 measured/observe SLI 或真实 emitter 指标。
- A2：告警表达式不得引用 `recommendation_offline_eval_metric_value`、`eligible_feed_item_count`、`collaborative_recall_lift` 等 objective_only 口径。
- A3：告警覆盖归因丢失、负反馈异常、召回路径 CTR 异常、旅行/精品消费断崖、UGC/数据工程供给失衡。
- A4：local_contract 固化告警名、Prometheus 指标、分桶标签、阈值和 alerts source group。
