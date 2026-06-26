# L3 Story：offline-replay-evaluation

## 功能说明

离线 replay 评估用过往请求、候选、曝光和反馈重放推荐策略，输出 NDCG、Recall@K、MAP、覆盖率、多样性、协同召回 lift、fact/affinity 解释 CTR、校准误差与晋级结论，作为线上 AB 前的质量门。

## 范围

- replay 数据集版本化，覆盖 request、candidate、served/impressed/click/dwell/negative/hide/takedown 与推荐归因字段。
- 指标：NDCG、Recall@K、MAP、coverage、diversity、calibration error、collaborative_recall_lift、fact/affinity explanation CTR。
- 按 channel、vertical、supply_source、recall_path、intersectionClass、scorer_variant 切分。
- 评估报告包含数据窗口、样本量、invalid 原因、policy/ranking/reason/scorer 版本、晋级与回滚建议。

## 非目标

- 本轮不实现批量调度、数据仓库 ETL 或深排训练 replay 平台。
- 不用离线指标替代线上 AB。

## 验收标准

- A1：指标名称与 `recommendation_slo.yaml` 对齐，并通过 `recommendation_offline_eval_metric_value{metric=...}` 暴露。
- A2：replay 可复现，报告包含数据窗口、样本量、invalid 原因、策略版本、排序版本、理由版本和 scorer variant。
- A3：低于门槛的策略不得进入线上 AB。
