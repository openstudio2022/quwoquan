# 开发任务：ml-model-integration-and-ab-test

## 模型集成（✅ 已完成）

- [x] 定义：ModelScorer 接口（ScoreBatch） → `scorer.go`
- [x] 实现：RuleScorer 增强基线（6 维特征公式） → `scorer.go`
- [x] 实现：RemoteModelScorer（ModelServiceClient 远程 ML 调用） → `scorer.go`
- [x] 实现：CascadeScorer（主模型超时/失败 → 降级到 RuleScorer） → `scorer.go`
- [x] 定义：FeatureProvider 接口 + UserFeatureVector → `feature.go`
- [x] 实现：FeatureStore 适配 FeatureProvider（MongoDB → UserFeatureVector） → `recommend_feature.go`
- [x] 定义：PreRanker 接口 + QualityPreRanker（时效过滤 + 互动密度粗排） → `prerank.go`
- [x] 定义：EmbeddingService 接口 + RemoteEmbeddingService → `embedding.go` + `prerank.go`
- [x] 集成：Engine 接入 ModelScorer / FeatureProvider / PreRanker → `engine.go`
- [x] 测试：ML 模型集成测试（自定义 Scorer 注入 / CascadeScorer 容灾 / 特征端到端） → `engine_test.go`

## AB 实验（⚡ 部分完成）

- [x] 实现：ScoringWeights AB 实验集成（WeightPresets） → `experiments.go`
- [x] 实现：ResolveWeights 动态权重解析 → `experiments.go`
- [ ] 实现：A/B 路由（runtime-experiments 集成 → 按 variant 选择 RuleScorer/RemoteModelScorer）
- [ ] 实现：实验分组维度 tag（rule vs ml）
- [ ] 实现：A/B 实验各组指标对比

## 可观测（🔲 待补充）

- [ ] 实现：推荐 CTR/曝光/留存 metric
- [ ] 实现：模型打分延迟 p50/p99 metric
- [ ] 实现：CascadeScorer fallback 频率 metric

## 下一步

- [ ] 部署：实际 ML 模型服务 + gRPC transport for ModelServiceClient
- [ ] 实现：内容 Embedding 生成 pipeline（PostCreated → RemoteEmbeddingService → 存储）
- [ ] 实现：在线学习闭环（FeedbackRecorder → 训练数据 → 模型更新）
