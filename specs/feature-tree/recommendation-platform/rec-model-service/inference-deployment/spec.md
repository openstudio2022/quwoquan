# L4 对象任务：inference-deployment（推理部署）

## 功能说明

- **推理镜像**：rec-model-service（Python FastAPI + LightGBM），健康检查 GET /health，从 ModelRegistry/OSS 加载 production 模型。
- **自建**：docker-compose 或 K8s 部署；与 content-service 同网或同集群，URL 配置连接。
- **云平台**：PAI-EAS 自定义 Processor 或内置 LightGBM Processor；火山 ML 在线服务；模型与数据存 OSS/TOS。

## 实现要点

- Dockerfile 与 docker-compose 新增 rec-model-service；环境变量连接 MongoDB/Redis/OSS。
- 文档或脚本：如何部署 PAI-EAS/火山推理服务。
- 部署后与 Go 集成验证：content-service 指向推理 URL 可正常打分。

## 约束

- 不硬编码云账号与密钥；与 quwoquan_service 部署方式兼容。

## 验收标准

- A1：docker-compose 可启动 rec-model-service，content-service 可调用。
- A8：部署步骤可文档化或脚本化复现。
