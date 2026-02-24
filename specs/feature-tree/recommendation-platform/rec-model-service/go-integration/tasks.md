# 开发任务：go-integration（L4）

- [ ] ModelPredictRequest 增加 Scenario 字段（或 context 中 scenario）（runtime/recommendation/scorer.go）
- [ ] HTTPModelServiceClient：实现 ModelServiceClient，POST 带 scenario 的 /v1/score（content-service 或 runtime 下）
- [ ] content-service config：rec_model_service.url、timeout、enabled
- [ ] content-service main.go：按配置组装 RemoteModelScorer + CascadeScorer，传入 scenario=content_feed
- [ ] 测试：HTTPModelServiceClient 模拟服务失败/超时，CascadeScorer 回退 RuleScorer
