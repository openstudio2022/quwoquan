# 开发任务：runtime-recommendation

## R1 — HotPath + Engine 基础（✅ 已完成）

- [x] 设计：双通道架构接口（HotPath + Engine） → `runtime/recommendation/engine.go`
- [x] 实现：Redis 热路径 — session_signals/exposed_set/negative_set/realtime_interest → `runtime/recommendation/hotpath.go`
- [x] 实现：信号上报接口 → `runtime/recommendation/hotpath.go`
- [x] 实现：召回模块（标签匹配 + 向量相似度） → `runtime/recommendation/engine.go`
- [x] 实现：排序模块（热度 + 新鲜度 + 实时信号加权） → `runtime/recommendation/engine.go`
- [x] 实现：重排模块（多样性 + 去重 + 负反馈过滤） → `runtime/recommendation/engine.go`
- [x] 实现：SessionID 维度隔离（userId:sessionId 复合 key） → `runtime/recommendation/hotpath.go`
- [x] 测试：热路径契约测试（miniredis） → `runtime/recommendation/engine_test.go`
- [x] 测试：引擎端到端测试 → `runtime/recommendation/engine_test.go`
- [x] gate：集成到 make gate

## R2 — 多路召回 + 投影器 + 特征存储（✅ 已完成）

- [x] 实现：TagRecallSource（MongoDB 标签召回） → `services/content-service/internal/infrastructure/recommendation/recall_sources.go`
- [x] 实现：HotRecallSource（热门内容召回） → 同上
- [x] 实现：ExploreRecallSource（随机探索召回） → 同上
- [x] 实现：AuthorRecallSource（关注作者召回） → 同上
- [x] 实现：VectorRecallSource（Atlas 向量搜索召回） → `vector_recall.go`
- [x] 实现：DiscoveryFeedProjector（rm_discovery_feed 读模型） → `discovery_projector.go`
- [x] 实现：RecommendFeatureProjector（rm_recommend_feature 特征存储） → `recommend_feature.go`
- [x] 实现：FeatureStore.GetUserFeatures → `recommend_feature.go`

## R3 — AB 实验 + 在线学习集成（✅ 已完成）

- [x] 实现：ScoringWeights AB 实验集成 → `runtime/recommendation/experiments.go`
- [x] 实现：WeightPresets 多组权重配置（control/engagement_heavy/freshness_heavy/explore_heavy）
- [x] 实现：ResolveWeights 动态权重解析 → `runtime/recommendation/experiments.go`
- [x] 实现：FeedbackRecorder — impression/engagement/scorecard 记录 → `runtime/recommendation/learning.go`
- [x] 实现：Pipeline 可观测指标（延迟/候选数/来源分布） → `runtime/recommendation/observability.go`
- [x] 测试：AB 实验路由测试 + 反馈录制测试 → `engine_test.go`

## R4 — 高并发性能优化（✅ 已完成）

- [x] 优化：GetSessionState 3 串行 Redis RTT → 并行（3x 延迟降低） → `hotpath.go`
- [x] 优化：ProcessSignalBatch 按 session 分组并行写入 → `hotpath.go`
- [x] 实现：BufferedHotPath 异步写入缓冲（channel + 批量刷写，火灾即忘） → `hotpath_buffer.go`
- [x] 实现：SessionCache L1 进程内缓存 + singleflight 防穿透（124ns/op vs 8931ns/op） → `session_cache.go`
- [x] 优化：Recall 超时保护（per-source 150ms deadline） → `engine.go`
- [x] 优化：Feedback 异步录制（fire-and-forget goroutine） → `engine.go`
- [x] 优化：Redis 连接池高并发调优（PoolSize=CPU×20, ReadTimeout=100ms） → `redis_client.go`
- [x] 定义：SessionReader / SignalProcessor 接口（读写路径解耦） → `hotpath.go`
- [x] 测试：SessionCache / BufferedHotPath / RecallTimeout / 并发 100 goroutine → `engine_test.go`
- [x] 测试：基准测试 6 项（GetFeed/SessionCache/MultiSource/ProcessSignal/GetSessionState/SessionCache） → `bench_test.go`

## R5 — 模型集成层（✅ 已完成）

- [x] 设计：7 阶段管线（Session → Recall → PreRank → Filter → Features → Score → Rerank） → `engine.go`
- [x] 定义：ModelScorer 接口（ScoreBatch） → `scorer.go`
- [x] 实现：RuleScorer 增强基线（6 维特征：实时标签+长期标签+作者亲和力+热度+新鲜度+参与率） → `scorer.go`
- [x] 实现：RemoteModelScorer（ModelServiceClient 远程 ML 调用） → `scorer.go`
- [x] 实现：CascadeScorer（主模型超时/失败 → 降级到 RuleScorer） → `scorer.go`
- [x] 定义：FeatureProvider 接口 + UserFeatureVector（TagAffinities/AuthorAffinities/EngagementRate） → `feature.go`
- [x] 实现：FeatureStore 适配 FeatureProvider（MongoDB → UserFeatureVector） → `recommend_feature.go`
- [x] 定义：PreRanker 接口 + QualityPreRanker（时效过滤+互动密度粗排） → `prerank.go`
- [x] 定义：EmbeddingService 接口 + RemoteEmbeddingService（HTTP 调用） → `embedding.go` + `prerank.go`
- [x] 集成：Engine 接入 ModelScorer + FeatureProvider + PreRanker（WithScorer/WithFeatureProvider/WithPreRanker） → `engine.go`
- [x] 测试：自定义 Scorer 注入 / CascadeScorer 容灾 / FeatureProvider 端到端 / RuleScorer 特征贡献 / PreRanker 过滤截断 → `engine_test.go`

## 下一步优化方向（🔲 待规划）

- [ ] 优化：Redis Pipeline 批量读（替换 3 个并行 goroutine 为单 RTT pipeline）
- [ ] 优化：Bloom Filter 替代 SMEMBERS 处理超大曝光集合
- [ ] 实现：实际 ML 模型服务部署 + gRPC transport for ModelServiceClient
- [ ] 实现：特征实时更新推送（FeatureStore 变更 → SessionCache 失效）
- [ ] 实现：内容 Embedding 生成 pipeline（PostCreated → RemoteEmbeddingService → 存储）
- [ ] 实现：在线学习反馈闭环（FeedbackRecorder → 训练数据 → 模型更新）
- [ ] 优化：对象池化减少 GC 压力（sync.Pool for candidate slices）
- [ ] 监控：推荐 CTR/曝光/留存 metric dashboard
