# L2 Business Capability：推荐评估与飞轮 (`evaluation-and-flywheel`)

> 所属领域：[`recommendation-platform`](../spec.md)
>
> 设计归属：[本层 design.md](./design.md)

## 1. 能力目标

推荐准确性评估、在线 AB 和真实流量训练晋升闭环。

## 2. 范围与非目标

### In Scope

- offline replay evaluation。
- online AB significance。
- real traffic training promotion。
- 非深排 P0 指标分桶：qualityScore、supplySource、vertical、recallPath、intersectionClass。
- P0+ 推荐商用归因看板：首页、旅行、精品、UGC、数据工程供给、recall_path、intersectionClass 和唯一 policyDigest。
- P1a 推荐商用归因告警：unknown attribution、负反馈、CTR、旅行/精品消费和供给来源失衡。

### Out of Scope

- 本能力不包含深排评估脚本、训练作业或模型发布逻辑。
- 深度排序模型平台轨。

## 3. Journey / Scenario 贡献

- [`JNY-011 / SCN-026`](../../spec.md#scn-026)
  - 本能力接收：该 Scenario 进入本能力边界的已授权主体与 canonical 输入。
  - 本能力处理：推荐准确性评估、在线 AB 和真实流量训练晋升闭环。
  - 本能力输出：直属 Story 组合产生的可观察结果与明确失败终态。
  - 失败时终态：保留已确认事实，并返回可恢复的 canonical failure。

## 4. Story



- [`offline-replay-evaluation`](./offline-replay-evaluation/spec.md)：定义“离线回放评估”的可观察主路径、失败语义及父能力交接。
- [`online-ab-significance`](./online-ab-significance/spec.md)：以稳定分桶、样本量和显著性阈值评估线上策略，样本不足时保持 hold。
- [`real-traffic-training-promotion`](./real-traffic-training-promotion/spec.md)：定义“真实流量训练晋升”的可观察主路径、失败语义及父能力交接。
- [`recommendation-commercial-alerting`](./recommendation-commercial-alerting/spec.md)：告警表达式不得引用 `recommendation_offline_eval_metric_value`、`eligible_feed_item_count`、`collaborative_recall_lift` 等 objective_only 口径。
- [`recommendation-observability-dashboard`](./recommendation-observability-dashboard/spec.md)：定义“推荐可观测性看板”的可观察主路径、失败语义及父能力交接。

## 5. 能力要求

<a id="req-001"></a>
### REQ-001 推荐评估飞轮 SIT

- 离线 replay 指标、在线 AB 显著性和真实流量训练晋升均有规格与验收。
- 所有指标命名与 recommendation_slo.yaml 对齐。
- 推荐商用归因看板必须读取与 SLO 相同的 canonical 指标。
- 商用归因告警必须引用同一 SLO 指标与阈值来源。
- 离线 replay report 与在线 AB report 必须使用同一指标字典，任一低于门槛时不得晋级。
- 深度排序模型平台属于独立能力范围，不作为本能力准出条件。

<a id="req-002"></a>
### REQ-002 真实流量训练晋升必须有评估报告和 rollback 层

- 真实流量训练晋升必须有评估报告和 rollback 层。

## 6. 契约与依赖

- 上游能力：[`recommendation-platform`](../spec.md) 声明的领域入口。
- 下游能力：本目录直接 Story 及其公开结果。
- 一致性要求：遵循本层或父 L1 DEC 声明的一致性边界。

## 7. 集成验收

<a id="sit-001"></a>
### SIT-001 推荐评估飞轮 SIT

- GIVEN 执行“推荐评估飞轮”所需的身份、输入与上游事实均有效。
- WHEN 参与者发起“推荐评估飞轮”对应动作。
- THEN 离线 replay 指标、在线 AB 显著性和真实流量训练晋升均有规格与验收。
- THEN 所有指标命名与 recommendation_slo.yaml 对齐。
- THEN 推荐商用归因看板与告警读取同一 SLO 指标与阈值来源。
- THEN 离线 replay report 与在线 AB report 使用同一指标字典，任一低于门槛时不得晋级。
- THEN 深度排序模型平台由独立能力验收，不影响本能力准出结论。

## 8. 开放事项

<a id="open-001"></a>
### OPEN-001 推荐评估飞轮 SIT

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`；目标：离线 replay 指标、在线 AB 显著性和真实流量训练晋升均有规格与验收。
- 完成判定：`SIT-001` 对应行为满足且真实测试 `spec_ref` 有效
