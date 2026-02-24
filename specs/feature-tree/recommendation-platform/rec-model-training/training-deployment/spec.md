# L4 对象任务：training-deployment（训练部署）

## 功能说明

- **训练镜像**：scripts/ml Dockerfile（LightGBM、pymongo、redis 等），供本地或云上训练任务使用。
- **调度**：PAI-DLC、火山 ML 工作流、cron 或事件驱动；按 scenario/datasetId 提交训练任务。
- **产出**：模型文件上传 OSS/TOS，元信息写入 rec_model_registry；推理服务（rec-model-service）从 Registry 拉取或挂载。

## 实现要点

- 训练镜像 Dockerfile 与启动入口（如 train.py --scenario --datasetId）。
- 文档或脚本：如何提交 PAI-DLC/火山训练任务；环境变量连接 MongoDB/Redis/OSS。

## 约束

- 不硬编码云账号与密钥；与 quwoquan_service 部署方式兼容。

## 验收标准

- A1：训练镜像可本地或云上跑通训练并写入 Registry。
- A8：部署与提交步骤可文档化或脚本化复现。
