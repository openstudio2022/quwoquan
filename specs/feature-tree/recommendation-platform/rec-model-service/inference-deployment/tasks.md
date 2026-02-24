# 开发任务：inference-deployment（L4）

- [ ] rec-model-service Dockerfile：Python FastAPI + LightGBM，健康检查
- [ ] docker-compose 新增 rec-model-service，与 content-service 同网
- [ ] 环境变量与 config：MongoDB/Redis/OSS 等连接信息
- [ ] 文档或脚本：PAI-EAS/火山推理部署（可选）
- [ ] 验收：docker-compose 启动后 content-service 可调用 rec-model-service 完成打分
