# runtime-redis 设计方案

## 设计动因

当前三套不兼容 Redis 接口（`repository.CacheAdapter`、`recommendation.RedisClient`、`context.RedisClient`）导致：
1. 每个服务自行构建 Redis 连接，无统一路由
2. metadata 声明的 8 个实体 `cache_layer: redis` 全部空转
3. chat 重构需要 realtime scene（seq/dedup/presence/Pub/Sub）无处安放

## 上游输入评审

- spec.md：清晰，3 scene 架构 + 统一接口 + 适配桥接已明确
- acceptance.yaml：R-A1~R-A13 覆盖接口/路由/桥接/弹性/可观测，可测量
- 无阻断项

## 对标输入分析

| 对标 | 借鉴 | 不借鉴 | 适用边界 |
|---|---|---|---|
| 飞书统一 Redis SDK | scene 路由 + 统一接口 | 内部 RPC 序列化（我们用 go-redis） | 中等规模服务集群 |
| 微信分场景 Redis | 按流量特征隔离 scene | 自研 proxy（我们用原生 Redis Cluster） | 写密集 vs 读密集分离 |
| Discord Redis 抽象 | Client 接口覆盖 K/V + Pub/Sub | Rust 客户端（我们用 Go） | Pub/Sub 与 K/V 混合 |

## 方案对比

### 方案 A：统一 Router + 三层 scene（选定）

在 `runtime/redis/` 新建统一包，定义 `Client` 接口（超集）和 `Router`（scene 路由），
现有接口通过 adapter 桥接，各服务一行 `redis.MustNewRouter(cfg)` 接入。

**优点**：
- 一套接口覆盖所有场景，上层零感知弹性
- scene 独立部署/扩缩，只改 config
- 现有代码通过 adapter 零回归迁移
- redis_keyspace.yaml 成为可执行契约（prefix → scene 自动路由）

**缺点**：
- 新增 `runtime/redis/` 包 + 3 个 adapter，约 800 行新代码
- 需迁移 content-service main.go 的 Redis 构建逻辑

**适用条件**：多服务共用 Redis，scene 有不同扩展需求

### 方案 B：各服务自建 Redis 客户端（现状）

保持现状，每个服务自己在 main.go 中构建 Redis 连接。

**优点**：零改动
**缺点**：
- 接口碎片化持续恶化
- 每新增服务重复 redis 构建样板
- chat 的 realtime scene 无法复用推荐的 cluster 配置逻辑
- 实体缓存永远无法自动激活

**适用条件**：单服务、单场景

## 选型决策

**选定方案 A**：统一 Router + 三层 scene。

理由：chat 重构 + realtime-gateway 是刚需触发点，不统一则两个服务各自重复 Redis 构建。
统一后，content-service 的 general cache 同时激活（metadata 声明的 Post/Circle 缓存自动生效）。

## 关键设计决策

### KD-1：`redis.Client` 接口定义（已定，不变）

超集覆盖 String/Hash/Set/Pub-Sub/Pipeline/Bytes。详见 spec.md §2.2。

### KD-2：场景实现路径

```
runtime/redis/
├── client.go           # Client 接口定义
├── router.go           # Router：scene 路由 + prefix 匹配
├── scene_pool.go       # ScenePool：standalone/cluster/memory 三模式连接池
├── config.go           # 配置结构 SceneConfig + PrefixRouting
├── adapter_cache.go    # NewCacheAdapter → repository.CacheAdapter 桥接
├── adapter_rec.go      # NewRecAdapter → recommendation.RedisClient 桥接
├── metrics.go          # Prometheus per-scene 指标
└── memory.go           # 内存实现（dev/test fallback）
```

### KD-3：ScenePool 三模式透明切换

```go
func newScenePool(cfg SceneConfig) (Client, error) {
    switch cfg.Mode {
    case "cluster":
        return newClusterClient(cfg)   // go-redis ClusterClient
    case "standalone":
        return newStandaloneClient(cfg) // go-redis Client
    default: // "memory" or empty
        return newMemoryClient(), nil   // 内存实现
    }
}
```

### KD-4：prefix 路由实现

Router 在初始化时构建 prefix trie（从 config.prefix_routing 加载），
`ForKey(key)` 做最长前缀匹配 → 返回对应 scene 的 Client。
未匹配 → fallback scene（默认 general）。

### KD-5：Pub/Sub 封装

`Client.Subscribe()` 返回 `Subscription` 接口（channel + goroutine 消费），
内部由 go-redis 的 `PubSub` 封装。cluster 模式下 Pub/Sub 走 shard pub/sub（Redis 7+）
或 global pub/sub（Redis 6），对上层透明。

### KD-6：adapter 桥接策略

| 现有接口 | adapter | 关键映射 |
|---|---|---|
| `repository.CacheAdapter` | `adapter_cache.go` | Get→GetBytes, Set→SetBytes, Del→Del |
| `recommendation.RedisClient` | `adapter_rec.go` | 1:1 映射 + PipelineRead → Pipeline batch |
| `context.RedisClient` | 删除接口，PageContext 直接接 `redis.Client` | 方法签名兼容 |

## Story 与测试层映射

| Story | 内容 | 测试层 |
|---|---|---|
| S1 | Client 接口 + ScenePool（三模式） | L2：miniredis standalone + cluster mock |
| S2 | Router + prefix 路由 | L2：3 个 miniredis 实例隔离验证 |
| S3 | adapter_cache + adapter_rec 桥接 | L2：现有 HotPath/Repository 测试不退化 |
| S4 | content-service 迁移 | L2：双 scene 集成测试 |
| S5 | Prometheus 指标 | L2：/metrics 端点校验 |

## 未来演进

- **Redis Bloom Filter**：exposed set 超大时替换 SAdd/SIsMember（触发：单 session 曝光 > 10 万）
- **Redis Streams**：event sourcing 场景替换 eventstore MongoDB（触发：事件量 > 100 万/天）
- **连接池动态调整**：基于 QPS 自动 scale pool size（触发：生产观察到池满阻塞）
