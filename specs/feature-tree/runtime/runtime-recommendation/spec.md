# L2 特性：runtime-recommendation

## 功能说明
- 双通道架构：Redis 热路径（session 级实时信号）+ 冷路径（离线特征 + ML 模型）。
- 热路径：session_signals（标签权重漂移）、exposed_set（去重）、negative_set（负反馈过滤）、realtime_interest（实时兴趣向量）。
- 推荐引擎：7 阶段管线 — Session → Recall → PreRank → Filter → FeatureAssembly → Score → Rerank。
- 模型层：RuleScorer 基线 / RemoteModelScorer 远程 ML / CascadeScorer 容灾降级。
- 性能层：SessionCache L1 缓存 + BufferedHotPath 异步写 + 并行读 + Redis Pool 调优。
- FeedType 支持：discovery / circle / follow / similar。

## 当前基线（2026-02-24）

### 已实现组件清单

| 文件 | 组件 | 职责 |
|------|------|------|
| `hotpath.go` | HotPath | Redis 实时信号读写（SessionReader + SignalProcessor） |
| `session_cache.go` | SessionCache | L1 进程内缓存 + singleflight（124ns/op） |
| `hotpath_buffer.go` | BufferedHotPath | 异步写入缓冲（channel + 批量刷写） |
| `engine.go` | Engine | 7 阶段推荐管线编排 |
| `scorer.go` | RuleScorer / RemoteModelScorer / CascadeScorer | 模型打分层 |
| `feature.go` | FeatureProvider / UserFeatureVector | 用户特征抽象 |
| `prerank.go` | QualityPreRanker | 时效过滤 + 互动密度粗排 |
| `embedding.go` | RemoteEmbeddingService | HTTP 外部 Embedding 调用 |
| `experiments.go` | WeightPresets / ResolveWeights | AB 实验权重解析 |
| `learning.go` | FeedbackRecorder | impression/engagement/scorecard 记录 |
| `observability.go` | PipelineMetrics | 管线可观测指标 |
| `redis_client.go` | RedisClientAdapter | Redis 适配 + 连接池调优 |
| `recommend_feature.go` | FeatureStore | MongoDB → FeatureProvider 适配 |

### 测试覆盖
| 文件 | 覆盖范围 |
|------|----------|
| `engine_test.go` | HotPath 契约 + Engine 端到端 + 模型集成 + CascadeScorer 容灾 + 特征 + PreRanker |
| `bench_test.go` | GetFeed / SessionCache / MultiSource / ProcessSignal / GetSessionState 基准 |

## 约束
- 信号上报延迟 < 50ms（热路径）。
- 已曝光内容不再推荐。
- 推荐策略参数可通过 experiments 灰度。
- CascadeScorer 保证 ML 不可用时降级到 RuleScorer。

## 验收标准
- A1：信号上报 → 偏好反映 → 下一批内容变化。✅ 通过
- A3：CascadeScorer 容灾降级。✅ 通过。A/B 路由待实现。
- A7：消费 recommend_impact 事件和 recommend_feature 字段。✅ 通过
- A8：热路径 + 引擎 + 模型集成 + 性能基准 均有测试。✅ 通过

## 特性树子节点（L3）

- **dual-channel-recommendation-engine**：双通道引擎（HotPath + Engine + 7 阶段管线），已基线完成。引擎通过 HTTP 调用**推荐平台**（L1 recommendation-platform）下的 **rec-model-service**（模型服务）完成 ML 打分；训练由 **rec-model-training** 独立负责，本节点不包含二者。

## 下一步优化方向
- 实现 rec-model-training 与 rec-model-service 全链路（见特性树 **recommendation-platform** 下两 L3：rec-model-training、rec-model-service）
- Redis Pipeline 替换并行 goroutine（进一步降低 RTT）
- Bloom Filter 处理超大曝光集合
- A/B 路由集成（按用户分组选择打分策略）
- CTR/曝光/留存 metric dashboard
- 内容 Embedding 生成 pipeline
