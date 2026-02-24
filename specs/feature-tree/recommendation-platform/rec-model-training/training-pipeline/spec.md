# L4 对象任务：training-pipeline（训练管线）

## 功能说明

- **样本**：从 rec_learning_events 拼接 impression 与 engagement，写入 rec_training_samples；样本带 scenario、用户/物品/交叉特征快照、多目标标签。
- **数据集**：DatasetManager 按时间切分 train/val/test，版本化写入 rec_datasets；支持滑动窗口与增量训练。
- **特征工程**：FeatureTransformer 与 feature_registry.yaml 统一特征名、类型、归一化；训练与推理共用同一注册表。
- **训练**：LightGBM 训练脚本（含增量 init_model）、超参搜索、离线评估（AUC/NDCG/GAUC）；产出模型文件与元信息。
- **注册**：ModelRegistry 写入 rec_model_registry，模型文件上传 OSS/TOS；支持 production 标记与热加载。

## 实现要点

- SampleJoiner（Go 或 Python）消费 events，可定时或事件驱动。
- 训练脚本支持 --scenario、--datasetId；导出模型与元信息供推理服务加载。
- 特征注册表与 Go 侧 OnlineFeatureStore / 推理请求体字段对齐。

## 约束

- 仅读 events/feature 等集合，不写业务库。
- 数据集切分按时间避免泄露；评估通过阈值后方可标记 production。

## 验收标准

- A1：从 events 到样本、到 dataset、到训练、到 Registry 全链路可跑通。
- A7：特征注册表与推理侧一致。
- A8：样本生成与训练脚本有自动化或文档化运行方式。
