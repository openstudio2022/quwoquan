# 开发任务：training-deployment（L4）

> 实施顺序建议在 training-pipeline 可跑通后进行。依赖 [training-pipeline/tasks.md](../training-pipeline/tasks.md) 的 train.py、ModelRegistry、config 约定。

## 1. 镜像与入口

- [ ] **训练镜像 Dockerfile**：LightGBM、pymongo、redis 等；建议路径如 `scripts/ml/Dockerfile` 或与 L3 约定一致。
- [ ] **训练入口脚本**：如 train.py --scenario --datasetId；与 pipeline 的 train.py 一致。
- [ ] **环境变量与 config**：MongoDB/Redis/OSS 连接信息；不硬编码云账号与密钥。

## 2. 调度与文档（可选）

- [ ] **文档或脚本**：PAI-DLC/火山训练任务提交步骤；环境变量与部署方式说明。

## 3. 验收

- [ ] **验收**：训练镜像可本地或云上跑通训练并写入 rec_model_registry；rec-model-service 可加载产出模型；部署与提交步骤可文档化或脚本化复现。
