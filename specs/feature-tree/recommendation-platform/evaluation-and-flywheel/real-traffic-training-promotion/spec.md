# L3 Story：real-traffic-training-promotion

## 功能说明

真实流量训练晋升把 gamma/prod 行为样本转为训练数据集，经过训练、评估、注册、推理 reload 和回滚门禁，形成可证明的“越用越准”闭环。

## 范围

- 真实行为样本进入 `rec_training_samples`。
- dataset、model registry、evaluation report 版本化。
- champion/challenger 与推理 reload 证据。
- 晋升失败回滚到上一稳定模型或 RuleScorer。

## 非目标

- 本轮不实现训练作业、模型注册或推理 reload。
- 不引入深度模型平台轨。

## 验收标准

- A1：训练数据来源、窗口、去重和标签定义清晰。
- A2：模型晋升必须先通过离线 replay 和在线 AB 口径。
- A3：推理 reload 有版本、时间、结果和回滚证据。
