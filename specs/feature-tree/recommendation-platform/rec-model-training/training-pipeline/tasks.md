# 开发任务：training-pipeline（L4）

> 实施顺序建议按 L3 [tasks.md](../tasks.md) 阶段 1（T1.1→T1.9）。字段与集合以 `contracts/metadata/_projections/` 为准。

## 1. 事件与样本（上游）

- [ ] **MongoSink**：rec_learning_events 持久化（Go）。若已由 content-service FeedbackRecorder 写入则跳过；否则实现写入，字段见 `_projections/learning_events.yaml`。
- [ ] **TrainingSample schema + SampleStore**：与 `_projections/training_samples.yaml` 一致（scenario、userId、targetId、userFeatures、itemFeatures、contextFeatures、labels、ts）。
- [ ] **SampleJoiner**：从 rec_learning_events 做 impression+engagement 窗口拼接，拼特征快照与多目标标签，写入 rec_training_samples（Go 或 Python Job）。

## 2. 数据集与特征

- [ ] **DatasetManager**：按时间切分 train/val/test，版本化；产出写入 rec_datasets（或约定格式），支持滑动窗口与增量训练（Go 或 Python）。
- [ ] **FeatureTransformer + feature_registry.yaml**：多 scenario 特征抽取/编码；feature_registry 与 rec-model-service 推理侧一致。

## 3. 训练与评估

- [ ] **train.py / incremental_train.py**：LightGBM 训练与增量训练（支持 --scenario、--datasetId）；产出模型文件与元信息。
- [ ] **evaluate.py**：AUC/NDCG/GAUC 离线评估；评估通过阈值后方可标记 production。

## 4. 注册与存储

- [ ] **ModelRegistry + ObjectStore**：元信息写入 rec_model_registry（字段见 `_projections/model_registry.yaml`），模型文件上传 OSS/TOS；支持 production 标记。

## 5. 验证

- [ ] **测试/脚本**：样本生成与训练链路可自动化或文档化复现；全链路 events→samples→dataset→train→Registry 可跑通。
