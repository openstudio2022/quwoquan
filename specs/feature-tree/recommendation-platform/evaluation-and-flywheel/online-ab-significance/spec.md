# L3 Story：online-ab-significance

## 功能说明

在线 AB 显著性规格定义 champion/challenger 对比、稳定分桶、最小样本量、指标窗口和显著性判定，防止策略凭主观感觉上线。

## 范围

- AB 分桶标签：channel、user_segment、recall_path、scorer_variant、exposure_pool、activity_segment、experiment_bucket。
- 北极星与护栏指标：有效消费、次留、完成率、CTR、负反馈率、重复曝光率、空 feed、fallback。
- 最小样本量和实验有效性。

## 非目标

- 本轮不实现 AB 框架或流量切分。
- 不以单次 local 测试替代线上显著性。

## 验收标准

- A1：AB 分桶稳定且可复现。
- A2：实验有效性进入 `ab_experiment_validity`。
- A3：实验报告包含显著性、样本量、分群和护栏指标。
