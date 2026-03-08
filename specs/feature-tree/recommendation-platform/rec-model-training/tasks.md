# 开发任务：rec-model-training（L3）

## 开发状态

- **状态**：Create 已完成，**可进入 Implement**（使用 `/dev` 按下列顺序实施）。
- **G1**：已满足。训练侧无独立 metadata 目录，依赖 `contracts/metadata/_projections/`（learning_events、training_samples、model_registry）；`make verify-metadata` 已通过。
- **代码/脚本落点**：训练为任务/作业形态，建议落点 `quwoquan_service/scripts/ml/`（或按约定 `services/rec-model-training/` 仅放脚本与配置），与 [design.md](../design.md) 一致。

## 与 _projections 对齐（必须）

实现时读写字段、集合、索引以以下 YAML 为准，禁止偏离：

| 用途 | 集合 | 操作 | 元数据文件 |
|------|------|------|------------|
| 事件输入 | rec_learning_events | 读 | `_projections/learning_events.yaml` |
| 样本输出 | rec_training_samples | 写 | `_projections/training_samples.yaml` |
| 模型元信息 | rec_model_registry | 写（训练）/ 读（推理） | `_projections/model_registry.yaml` |
| 特征读 | rm_recommend_feature | 读 | 已有 recommend_feature 投影 |

---

## 建议实施顺序（按依赖）

### 阶段 0：契约与落点（先做）

- [ ] **T0.1** 确认 `feature_registry` 与 rec-model-service 推理侧约定一致（可先建 `feature_registry.yaml` 占位或初版）。
- [ ] **T0.2** 确定并创建代码落点目录（如 `scripts/ml/`），在 README 或 L4 tasks 中写明。

### 阶段 1：training-pipeline（L4）

按 [training-pipeline/tasks.md](training-pipeline/tasks.md) 顺序：

- [ ] **T1.1** MongoSink：rec_learning_events 持久化（Go，若尚未由 content-service 写入则实现）。
- [ ] **T1.2** TrainingSample schema + SampleStore：与 `_projections/training_samples.yaml` 一致，含 scenario、特征快照、标签。
- [ ] **T1.3** SampleJoiner：impression+engagement 窗口拼接 + 特征快照 + 标签生成（Go 或 Python Job）。
- [ ] **T1.4** DatasetManager：时间切分 train/val/test、版本化、rec_datasets（Go 或 Python）。
- [ ] **T1.5** FeatureTransformer + feature_registry.yaml：多 scenario 特征抽取/编码，与推理侧一致。
- [ ] **T1.6** train.py / incremental_train.py：LightGBM 训练与增量训练。
- [ ] **T1.7** evaluate.py：AUC/NDCG/GAUC 离线评估。
- [ ] **T1.8** ModelRegistry + ObjectStore：元信息写入 rec_model_registry，模型文件上传 OSS/TOS。
- [ ] **T1.9** 测试/脚本：样本生成与训练链路可自动化或文档化复现。

### 阶段 2：training-deployment（L4）

按 [training-deployment/tasks.md](training-deployment/tasks.md) 顺序：

- [ ] **T2.1** 训练镜像 Dockerfile（LightGBM、pymongo、redis 等）。
- [ ] **T2.2** 训练入口脚本（如 train.py --scenario --datasetId）及环境变量/config（MongoDB/Redis/OSS）。
- [ ] **T2.3** 文档或脚本：PAI-DLC/火山训练任务提交（可选）。
- [ ] **T2.4** 验收：训练→注册可跑通，rec-model-service 可加载产出模型。

### 阶段 3：L3 收尾

- [ ] **T3.1** 门禁：`make verify-metadata` 通过；脚本/文档可复现全链路。
- [ ] **T3.2** 与 L1 acceptance 对齐：A1（events→样本→dataset→训练→Registry）、A7（feature_registry 一致）、A8（可脚本化复现）。

---

## 原有清单（与上面对应）

- [ ] training-pipeline：样本、数据集、特征、训练、注册全链路见 [training-pipeline/tasks.md](training-pipeline/tasks.md)
- [ ] training-deployment：训练镜像、PAI/火山任务、调度见 [training-deployment/tasks.md](training-deployment/tasks.md)
- [ ] 读写与 _projections 一致：rec_learning_events（读）、rec_training_samples（写）、rec_model_registry（写）、rm_recommend_feature（读）
- [ ] feature_registry 与 rec-model-service 共用；训练产出可被推理侧从 ModelRegistry/OSS 加载
- [ ] 门禁：make verify-metadata 通过；脚本/文档可复现
