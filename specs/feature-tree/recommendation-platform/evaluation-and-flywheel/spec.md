# L2 特性：evaluation-and-flywheel

## 功能说明

`evaluation-and-flywheel` 是推荐平台的评估与飞轮能力，负责让“越用越准”可被离线 replay、在线 AB 和真实流量训练晋升证明。它不拥有线上 feed 编排，也不直接写业务库。

## 范围

- 离线 replay 评估：NDCG、Recall@K、MAP、覆盖率、多样性、校准误差。
- 在线 AB 显著性：样本量、分桶稳定性、分群切分、champion/challenger。
- 真实流量训练闭环：gamma/prod 行为样本 → 数据集 → 训练 → 评估 → 注册 → 推理 reload。

## 非目标

- 本轮不实现训练作业、评估脚本或模型发布逻辑。
- 不引入深度排序模型平台轨。

## 验收标准

- A1：离线 replay 指标与 `recommendation_slo.yaml` 同名。
- A2：在线 AB 具备最小样本量和显著性口径。
- A3：真实流量训练晋升必须有评估报告和 rollback 层。
- A4：训练和推理仍保持 recommendation-platform 既有边界。
