# L5 叶子：sample-feature-train-registry

训练管线最小可交付单元：样本生成与存储、特征工程与注册表、模型训练与评估、模型注册与存储。保证 events 到 samples、dataset、model、registry 全链路打通，特征注册表与推理侧一致。

## 验收

- A1：SampleJoiner 产出带 scenario 的样本；DatasetManager 产出 train/val/test；train.py 产出模型；ModelRegistry 记录元信息。
- A7：feature_registry 与推理一致。A8：可脚本化跑通全链路。
