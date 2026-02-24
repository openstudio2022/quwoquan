# L3 子特性：dual-channel-recommendation-engine

## 功能说明
- **双通道架构**：HotPath（Redis 实时信号）+ ColdPath（离线特征 + ML 模型）+ Engine（7 阶段管线）。
- **HotPath**：session_signals、exposed_set、negative_set、realtime_interest；信号上报 < 50ms。
- **ColdPath**：从 RecommendFeatureProjector 的 ReadModel 获取离线特征；FeatureStore 适配 FeatureProvider 接口。
- **Engine**：7 阶段管线 → SessionState → Recall → PreRank → Filter → FeatureAssembly → Score → Rerank。

## 已实现架构

### 读写路径分离
- **SessionReader** 接口：统一读路径，HotPath / SessionCache 均实现。
- **SignalProcessor** 接口：统一写路径，HotPath / BufferedHotPath 均实现。

### 7 阶段推荐管线
```
GetFeed(req) →
  ① Session 加载 (SessionReader.GetSessionState)
  ② 多路并行召回 (CandidateSource[].Fetch, per-source 150ms deadline)
  ③ 预排 (PreRanker.PreRank → 时效过滤 + 互动密度粗排)
  ④ 过滤 (曝光去重 + 负反馈 + 全局去重)
  ⑤ 特征组装 (FeatureProvider.GetFeatures → ScoringFeatures)
  ⑥ 模型打分 (ModelScorer.ScoreBatch)
  ⑦ 重排 (作者去重 + 多样性 + 探索率)
→ FeedResponse
```

### 性能保障层
| 组件 | 作用 | 性能效果 |
|------|------|----------|
| SessionCache | L1 进程内缓存 + singleflight | 124ns/op vs 8931ns/op |
| BufferedHotPath | 异步写入缓冲（channel + 批量刷写） | 写操作不阻塞请求路径 |
| HotPath 并行读 | 3 Redis 读并行执行 | 3x 延迟降低 |
| Recall 超时保护 | per-source 150ms deadline | 慢源不阻塞管线 |
| Feedback 异步 | fire-and-forget goroutine | 不阻塞响应 |
| Redis Pool 调优 | PoolSize=CPU×20, ReadTimeout=100ms | 高并发吞吐 |

### 模型集成层
| 组件 | 职责 | 实现 |
|------|------|------|
| ModelScorer | 统一打分接口 | RuleScorer / RemoteModelScorer / CascadeScorer |
| FeatureProvider | 用户特征供给 | NullFeatureProvider / FeatureStore(MongoDB) |
| PreRanker | 粗排截断 | NullPreRanker / QualityPreRanker |
| EmbeddingService | 向量生成 | RemoteEmbeddingService(HTTP) |

## 约束
- 消费 recommend_impact 事件和 recommend_feature 字段。
- 推荐策略参数可通过 experiments 灰度。
- CascadeScorer 保证 ML 模型不可用时自动降级到 RuleScorer。

## 验收标准
- A1：Engine 端到端 7 阶段管线正确。
- A3：CascadeScorer fallback 验证通过。
- A7：消费 recommend_impact 和 recommend_feature。
- A8：Engine 有端到端测试 + 基准测试 + 模型集成测试。
