# L5 叶子：docker-and-cloud（推理服务部署）

## 功能说明

部署的最小可交付单元：rec-model-service 推理镜像与 docker-compose；可启动推理服务并与 content-service 联调；可选云平台（PAI-EAS/火山）推理部署。

## 验收标准

- A1：docker-compose 启动后 content-service 可调用 rec-model-service 完成打分。
- A8：部署步骤可文档化或脚本化复现。
