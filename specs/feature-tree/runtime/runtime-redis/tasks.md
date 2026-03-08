# runtime-redis 任务列表

## 当前交付任务

- [x] T1: [metadata] 升级 `contracts/metadata/_shared/redis_keyspace.yaml` v2（含 scene_routing + realtime 场景）
- [x] T2: [runtime] 创建 `runtime/redis/client.go` — Client 统一接口定义
- [x] T3: [runtime] 创建 `runtime/redis/config.go` — SceneConfig + PrefixRouting 配置结构
- [x] T4: [runtime] 创建 `runtime/redis/scene_pool.go` — standalone/cluster/memory 三模式连接池
- [x] T5: [runtime] 创建 `runtime/redis/router.go` — Router 实现（Scene 显式路由 + ForKey prefix 路由）
- [x] T6: [runtime] 创建 `runtime/redis/memory.go` — 内存实现（dev/test fallback）
- [x] T7: [runtime] 创建 `runtime/redis/adapter_cache.go` — NewCacheAdapter 桥接 repository.CacheAdapter
- [x] T8: [runtime] 创建 `runtime/redis/adapter_rec.go` — NewRecAdapter 桥接 recommendation.RedisClient + RedisPipeliner
- [x] T9: [runtime] 创建 `runtime/redis/metrics.go` — 结构化 per-scene 指标（InstrumentedClient 装饰器）
- [x] T10: [runtime] 修改 `runtime/context/page_context.go` — 删除自定义 RedisClient 接口，直接接 redis.Client
- [x] T11: [迁移] 修改 `content-service/cmd/api/main.go` — 替换 buildRecRedisClient 为 redis.Router + toSceneConfig
- [x] T12: [测试] 创建 `runtime/redis/router_test.go` — 三 scene 隔离 + prefix 路由 + 模式切换 (22 tests)
- [x] T13: [测试] 创建 `runtime/redis/adapter_test.go` — CacheAdapter + RecAdapter + HotPath 集成 (6 tests)
- [x] T14: [测试] 创建 `content-service/tests/redis_router_contract_test.go` — 双 scene 集成测试
- [x] T15: [门禁] make gate 通过

## 搁置任务

- [ ] Redis Bloom Filter adapter（重启条件：单 session 曝光 ID > 10 万）
- [ ] Redis Streams adapter（重启条件：eventstore 事件量 > 100 万/天）
- [ ] 连接池动态调整（重启条件：生产监控观察到池满阻塞）

## 未来演进任务

- [ ] Lua 脚本执行器（复杂原子操作需求出现时）
- [ ] Redis Sentinel 模式支持（高可用需求但不需 cluster 分片时）
