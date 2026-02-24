# L3 组件：rec-model-training（训练集部署工程服务）

## 功能说明

- **定位**：推荐平台下的训练工程服务，对接不同模型训练场景（content_feed / circle_discovery / friend_suggestion），产出模型与元信息写入 ModelRegistry + OSS/TOS，供模型服务加载。
- **职责**：样本生成、数据集管理、特征工程、模型训练、模型注册；部署形态为**任务/作业**（训练镜像 + PAI-DLC/火山调度），非常驻 HTTP 服务。
- **技术栈**：Python（LightGBM、pymongo、redis 等）；与 rec-model-service 共用 feature_registry、ModelRegistry 契约。

## 与现有系统关系

- **L1**：recommendation-platform（推荐/ML 平台）
- **本节点 L3**：rec-model-training；下游为 rec-model-service（推理侧从 Registry/OSS 加载本服务产出的模型）。

## 子节点（L4）

| L4 | 说明 |
|----|------|
| training-pipeline | 样本、数据集、特征、训练、注册全链路 |
| training-deployment | 训练镜像、PAI/火山训练任务、调度与脚本 |

## 约束

- 仅读 rec_learning_events、rec_training_samples、rm_recommend_feature 等；写 rec_training_samples、rec_datasets、rec_model_registry 及 OSS/TOS。
- 特征注册表与推理侧（rec-model-service）一致。

## 验收标准（概要）

- A1：从 events → 样本 → dataset → 训练 → Registry 全链路可跑通。
- A7：feature_registry 与推理侧一致。
- A8：样本生成与训练可脚本化/文档化复现。
