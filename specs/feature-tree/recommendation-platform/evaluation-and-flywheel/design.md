# L2 Design：推荐评估与飞轮 (`evaluation-and-flywheel`)

> 对应规格：[L2 spec](./spec.md)

> 设计触发原因：“推荐准确性评估、在线 AB 和真实流量训练晋升闭环”需要 `offline-replay-evaluation`、`online-ab-significance`、`real-traffic-training-promotion`、`recommendation-commercial-alerting`、`recommendation-observability-dashboard` 共享状态 owner、契约或质量边界。

## 1. 背景、目标与非目标

- 设计目标：推荐准确性评估、在线 AB 和真实流量训练晋升闭环。
- 非目标：复制字段 schema、实现任务、测试排列组合或执行历史。

## 2. Story 协作与状态流

- [`offline-replay-evaluation`](./offline-replay-evaluation/spec.md)：定义“离线回放评估”的可观察主路径、失败语义及父能力交接。
- [`online-ab-significance`](./online-ab-significance/spec.md)：以稳定分桶、样本量和显著性阈值评估线上策略，样本不足时保持 hold。
- [`real-traffic-training-promotion`](./real-traffic-training-promotion/spec.md)：定义“真实流量训练晋升”的可观察主路径、失败语义及父能力交接。
- [`recommendation-commercial-alerting`](./recommendation-commercial-alerting/spec.md)：告警表达式不得引用 `recommendation_offline_eval_metric_value`、`eligible_feed_item_count`、`collaborative_recall_lift` 等 objective_only 口径。
- [`recommendation-observability-dashboard`](./recommendation-observability-dashboard/spec.md)：定义“推荐可观测性看板”的可观察主路径、失败语义及父能力交接。

## 3. 端云与数据流

- 上游能力：[`recommendation-platform`](../spec.md) 声明的领域入口。
- 下游能力：本目录直接 Story 及其公开结果。
- 一致性要求：遵循本层或父 L1 DEC 声明的一致性边界。

## 4. 关键决策

<a id="dec-001"></a>
### DEC-001 离线 Replay 未达阈值不得晋升真实流量
- 决策：离线 Replay 未达阈值不得晋升真实流量。
- 理由：推荐准确性评估、在线 AB 和真实流量训练晋升闭环。
- 被否决方案：由调用方、页面或脚本复制本层状态并绕过公开契约。
- 约束与影响：实现只能细化对应规格与 canonical contract；冲突时先修正规格或契约。
- 关联要求：`REQ-001`
- 影响 Story：[`offline-replay-evaluation`](./offline-replay-evaluation/spec.md)、[`online-ab-significance`](./online-ab-significance/spec.md)、[`real-traffic-training-promotion`](./real-traffic-training-promotion/spec.md)、[`recommendation-commercial-alerting`](./recommendation-commercial-alerting/spec.md)、[`recommendation-observability-dashboard`](./recommendation-observability-dashboard/spec.md)
- 关联验收：`SIT-001`

## 5. 失败与恢复

- 失败类型：权限拒绝、依赖超时、版本冲突或持久化失败。
- 可见结果：调用方收到可区分的 canonical failure 或规格明确允许的降级结果；任何失败均不写入成功事实。
- 恢复动作：调用方按 canonical recovery action 重试、刷新或停止；不得自行合成成功结果。
- 禁止 fallback：不得回退到 Mock、旧 wire、双读双写或页面本地写副本。

## 6. 质量与观测

- SLO 与指标：`quwoquan_service/services/content-service/observability/slo/recommendation_slo.yaml`。
