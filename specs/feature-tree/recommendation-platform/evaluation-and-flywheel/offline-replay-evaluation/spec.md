# L3 Story：offline-replay-evaluation

## 功能说明

离线 replay 评估用历史请求、候选、曝光和反馈重放推荐策略，输出 NDCG、Recall@K、MAP、覆盖率、多样性、校准误差等指标，作为线上 AB 前的质量门。

## 范围

- replay 数据集版本化。
- 指标：NDCG、Recall@K、MAP、coverage、diversity、calibration error。
- 按 channel、segment、recall_path、scorer_variant 切分。
- 评估报告进入模型/策略晋升门。

## 非目标

- 本轮不实现 replay 脚本。
- 不用离线指标替代线上 AB。

## 验收标准

- A1：指标名称与 `recommendation_slo.yaml` 对齐。
- A2：replay 可复现，报告包含数据窗口、样本量、策略版本。
- A3：低于门槛的策略不得进入线上 AB。
