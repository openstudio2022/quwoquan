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
