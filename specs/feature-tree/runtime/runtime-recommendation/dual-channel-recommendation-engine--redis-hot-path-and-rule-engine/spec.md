# L4 对象任务：redis-hot-path-and-rule-engine

## 功能说明
- **Redis 热路径**：session_signals（标签权重漂移）、exposed_set（去重）、negative_set（负反馈过滤）、realtime_interest（实时兴趣向量）；key 格式 `session:{user_id}:{session_id}:*`。
- **信号上报接口**：POST /v1/content/feed/signal；body 含 content_id、signal_type（view/like/dislike）、metadata。
- **规则引擎**：RuleScorer 6 维特征评分 + 可配置权重。
- **性能保障**：SessionCache + BufferedHotPath + 并行读写 + Redis 连接池调优。

## 已实现架构

### 接口分层
| 接口 | 实现 | 职责 |
|------|------|------|
| SessionReader | HotPath, SessionCache | 读取 session 状态 |
| SignalProcessor | HotPath, BufferedHotPath | 写入行为信号 |
| RedisClient | RedisClientAdapter | 抽象 Redis 操作 |

### 性能优化实现
| 优化项 | 实现方式 | 文件 |
|--------|----------|------|
| 读并行化 | 3 个 Redis 读 WaitGroup 并行 | `hotpath.go` |
| 写并行化 | session 分组 + WaitGroup 并行写 | `hotpath.go` |
| L1 缓存 | 进程内 SessionState 缓存 + singleflight 防穿透 | `session_cache.go` |
| 异步写入 | channel 缓冲 + 批量刷写（fire-and-forget） | `hotpath_buffer.go` |
| 连接池 | PoolSize=CPU×20, MinIdleConns=CPU×5, ReadTimeout=100ms | `redis_client.go` |

### RuleScorer 评分公式
```
score = w_popularity × 热度 + w_freshness × 新鲜度 + w_realtime × 实时标签命中
       + w_longterm × 长期标签亲和力 + w_author × 作者亲和力 + w_engagement × 参与率
```

## 约束
- 信号上报延迟 < 50ms。
- 已曝光内容不再推荐。
- 契约测试使用 miniredis。
- BufferedHotPath 满载时背压丢弃 + 日志告警。

## 验收标准
- A1：热路径 + 规则引擎端到端正确。
- A2：SessionCache 命中 124ns/op（vs 直连 8931ns/op）。
- A8：热路径契约测试 + 规则引擎单元测试 + 基准测试。

## Folded current node `ml-model-integration-and-ab-test`

# L5 横切：ml-model-integration-and-ab-test

## 功能说明
- **ML 模型集成**：ModelScorer 抽象统一打分接口；支持 RuleScorer 基线 / RemoteModelScorer 远程 ML / CascadeScorer 容灾降级。
- **特征工程**：FeatureProvider 抽象用户特征供给；UserFeatureVector 包含 TagAffinities / AuthorAffinities / EngagementRate；FeatureStore 适配 MongoDB 读模型。
- **预排阶段**：PreRanker 抽象粗排截断；QualityPreRanker 实现时效过滤 + 互动密度排序。
- **Embedding 服务**：EmbeddingService 抽象向量生成；RemoteEmbeddingService 实现 HTTP 调用外部 API。
- **A/B 灰度**：推荐策略通过 runtime-experiments 灰度；支持规则引擎 vs ML 模型分组（权重层已完成，路由层待补）。

## 已实现架构

### 模型打分层
```
ModelScorer interface
├── RuleScorer          (增强基线: 6维特征公式)
├── RemoteModelScorer   (HTTP → ModelServiceClient → ML 模型)
└── CascadeScorer       (primary + fallback + timeout)
```

### 特征组装
```
FeatureProvider interface
├── NullFeatureProvider  (无特征 → 兜底)
└── FeatureStore         (MongoDB rm_recommend_feature → UserFeatureVector)
                          ├── TagAffinities      map[string]float64
                          ├── AuthorAffinities   map[string]float64
                          ├── TotalLikes/Views/Shares
                          └── EngagementRate      (likes+shares) / max(views, 1)
```

### 预排阶段
```
PreRanker interface
├── NullPreRanker       (透传)
└── QualityPreRanker    (MaxAge 时效过滤 + engagementDensity 粗排 + freshness 加成)
```

### CascadeScorer 容灾
- 主模型 (RemoteModelScorer) 超时或失败 → 自动降级到 fallback (RuleScorer)
- 降级日志包含原始错误信息 + 候选数量
- 超时可配置（WithTimeout option）

## 约束
- 实验配置与 experiments 元数据一致。
- ML 模型 fallback 到规则引擎（CascadeScorer 保证）。
- FeatureProvider 有独立超时（featureTimeout），超时不阻塞打分。

## 验收标准
- A1：ModelScorer 自定义注入 + 端到端打分正确。
- A3：CascadeScorer 容灾降级验证通过。A/B 路由待实现。
- A4：CTR/曝光/留存可监控（待实现 metric dashboard）。
- A8：ML 集成测试 + CascadeScorer 容灾测试 + 特征端到端测试 + PreRanker 测试。
