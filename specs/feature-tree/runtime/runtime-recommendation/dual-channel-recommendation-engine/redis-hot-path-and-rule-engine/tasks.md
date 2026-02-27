# 开发任务：redis-hot-path-and-rule-engine

## 已完成

- [x] 实现：Redis 热路径 — session_signals/exposed_set/negative_set/realtime_interest → `hotpath.go`
- [x] 实现：信号上报接口 POST /v1/content/feed/signal → `content_handler.go`
- [x] 实现：召回模块（标签匹配 + 向量相似度） → `engine.go`
- [x] 实现：排序模块（热度 + 新鲜度 + 实时信号加权） → `engine.go` → `scorer.go`
- [x] 实现：重排模块（多样性 + 作者去重 + 负反馈过滤 + 探索率） → `engine.go`
- [x] 实现：GET /v1/content/feed 接口（游标分页） → `content_handler.go`
- [x] 优化：GetSessionState 3 读并行（WaitGroup） → `hotpath.go`
- [x] 优化：ProcessSignalBatch session 分组并行写 → `hotpath.go`
- [x] 实现：SessionReader / SignalProcessor 接口（读写解耦） → `hotpath.go`
- [x] 实现：BufferedHotPath 异步写入缓冲 → `hotpath_buffer.go`
- [x] 实现：SessionCache L1 进程内缓存 + singleflight → `session_cache.go`
- [x] 优化：Redis 连接池调优（PoolSize/MinIdleConns/ReadTimeout/WriteTimeout） → `redis_client.go`
- [x] 增强：RuleScorer 6 维特征评分（实时标签 + 长期标签 + 作者亲和力 + 热度 + 新鲜度 + 参与率） → `scorer.go`
- [x] 测试：热路径契约测试（miniredis） → `engine_test.go`
- [x] 测试：规则引擎单元测试 + RuleScorer 特征贡献验证 → `engine_test.go`
- [x] 测试：SessionCache / BufferedHotPath 测试 → `engine_test.go`
- [x] 测试：基准测试（HotPath 并行读/写 + SessionCache） → `bench_test.go`
- [x] gate：集成到 make gate

## 下一步（已在 redis-storage-elastic-infra 跟踪）

- [x] 优化：Redis Pipeline 替换并行 goroutine（3 RTT → 1 RTT）
  - 已实现：`PipelineRead` 接口 + `RedisClientAdapter.PipelineRead` + `RedisClusterAdapter.PipelineRead`
  - 详见：`redis-storage-elastic-infra/redis-cluster-protocol` 节点
- [ ] 优化：Bloom Filter 处理超大 exposed_set（见 `redis-cluster-protocol` 未来演进任务）
- [ ] 优化：sync.Pool 复用 candidate 切片
