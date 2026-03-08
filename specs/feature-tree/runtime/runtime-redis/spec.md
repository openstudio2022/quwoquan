# L2 规格：runtime-redis — 统一 Redis 路由层

> 平台级 Redis 基础设施，所有服务通过统一接口 + scene 路由访问 Redis，上层无感弹性扩缩。

## 1. 背景

### 1.1 现状问题

当前 Redis 使用存在三个核心缺陷：

**接口碎片化** — 三套不兼容接口各自为政：

| 接口 | 包 | 方法签名 | 使用者 |
|---|---|---|---|
| `CacheAdapter` | `runtime/repository` | Get/Set/Del ([]byte) | Repository 缓存装饰器（**无服务接入**） |
| `RedisClient` (rec) | `runtime/recommendation` | Get/Set/Del/SAdd/HIncrByFloat/Pipeline (string) | HotPath（content-service） |
| `RedisClient` (ctx) | `runtime/context` | Get/Set/Del (string, **参数类型不同**) | PageContext |

**scene 路由只在文档不在代码** — `redis_keyspace.yaml` 声明了 rec/general 两个场景，但：
- `redis.general` 在 config 中预留却从未创建客户端
- `repository.Factory.WithCache()` 存在但无服务调用
- metadata 声明的 `cache_layer: redis`（Post/Circle/Conversation/UserProfile 等 8 个实体）全部空转

**新场景无处安放** — chat 重构需要的 seq INCR、clientMsgId 幂等 SET NX、在线状态 presence、Pub/Sub 跨节点 fanout 均需要独立 Redis scene，当前架构无法承载。

### 1.2 业界对标

| 平台 | Redis 架构 | 场景分离 |
|---|---|---|
| 飞书 | 统一 Redis SDK + 场景路由 | IM / 推送 / 缓存 / 计数 独立集群 |
| 微信 | 分场景 Redis | 时间线热路径 vs 点赞计数 vs 缓存 独立扩容 |
| Discord | Redis Cluster + 场景分离 | 消息路由 / 状态 / 缓存 独立集群 |
| Slack | 统一 Redis 抽象层 | 不同 workspace 隔离到不同 cluster |

### 1.3 从 runtime-recommendation 提升的理由

当前 Redis 弹性基础设施挂在 `runtime-recommendation/redis-storage-elastic-infra` 下，但 Redis 是**平台级横切能力**，不从属于推荐：
- chat-service 需要 realtime scene（seq/dedup/presence/Pub/Sub）
- realtime-gateway 需要 realtime scene（跨节点 fanout）
- user-service 需要 general scene（blocked_set/device_tokens/login_fail）
- 所有服务需要 general scene（实体缓存）

提升为 L2 `runtime-redis`，与 `runtime-repository`、`runtime-messaging`、`runtime-observability` 平级，符合 runtime 统一能力的定位。

## 2. 核心设计

### 2.1 架构总览

```
┌──────────────────────────────────────────────────────────────┐
│  上层消费者（不感知 Redis 拓扑和弹性）                         │
│  Repository.Cache │ HotPath │ SeqGen │ Dedup │ Pub/Sub │ ... │
└────────┬──────────┬─────────┬────────┬───────┬───────────────┘
         │          │         │        │       │
         ▼          ▼         ▼        ▼       ▼
┌──────────────────────────────────────────────────────────────┐
│  runtime/redis.Router                                        │
│  ┌────────────────────────────────────────────────────────┐  │
│  │  Scene 路由表（from config + redis_keyspace.yaml）      │  │
│  │    "rec:*"       → rec ScenePool                       │  │
│  │    "cache:*"     → general ScenePool                   │  │
│  │    "page_ctx:*"  → general ScenePool                   │  │
│  │    "rt:*"        → realtime ScenePool                  │  │
│  │    "seq:*"       → realtime ScenePool                  │  │
│  │    "presence:*"  → realtime ScenePool                  │  │
│  │    "dedup:*"     → realtime ScenePool                  │  │
│  │    fallback      → general ScenePool                   │  │
│  └────────────────────────────────────────────────────────┘  │
└──────────┬──────────────────┬──────────────────┬─────────────┘
           ▼                  ▼                  ▼
    ┌─────────────┐    ┌─────────────┐    ┌─────────────┐
    │  ScenePool   │    │  ScenePool   │    │  ScenePool   │
    │  "rec"       │    │  "general"   │    │  "realtime"  │
    │  cluster     │    │  standalone  │    │  cluster     │
    │  独立扩容    │    │  独立扩容    │    │  独立扩容    │
    └─────────────┘    └─────────────┘    └─────────────┘
```

### 2.2 统一接口 `redis.Client`

覆盖当前三套接口的超集 + chat/realtime 新需求：

| 操作类别 | 方法 | 覆盖来源 |
|---|---|---|
| String | Get / Set / SetNX / Del / Incr / Expire | CacheAdapter + rec.RedisClient + ctx.RedisClient |
| Hash | HSet / HGet / HGetAll / HIncrByFloat | rec.RedisClient (HotPath) |
| Set | SAdd / SMembers / SIsMember | rec.RedisClient (HotPath) |
| Pub/Sub | Publish / Subscribe | 新增（realtime-gateway fanout） |
| Pipeline | Pipeline() → batch exec | rec.RedisPipeliner |
| Bytes | GetBytes / SetBytes | CacheAdapter (Repository cache) |

### 2.3 `redis.Router` — scene 路由

| 方法 | 说明 |
|---|---|
| `Scene(name string) Client` | 显式指定 scene，获取 scene 级 Client |
| `ForKey(key string) Client` | 从 key prefix 自动路由到对应 scene（查路由表） |
| `Close() error` | 关闭所有 scene 连接池 |

上层消费者推荐使用 `Scene()` 显式路由（语义清晰），`ForKey()` 用于 Repository cache 等 key 由 metadata 驱动的场景。

### 2.4 Scene 划分

| Scene | 流量特征 | 典型 key prefix | 独立部署理由 |
|---|---|---|---|
| **rec** | 高 QPS 写密集，session 级，pipeline 读 | `rec:` | 推荐热路径独立扩容，hash tag `{userId}` |
| **general** | 读多写少，TTL 较长，延迟容忍度高 | `cache:`, `page_ctx:`, `blocked_set:`, `counter:`, `reaction:`, `content_analysis:`, `comment_summary:`, `suggested_actions:`, `device_tokens:`, `login_fail:` | 实体缓存 + 安全限流 + 计数缓冲 |
| **realtime** | 超低延迟，Pub/Sub 重，INCR 原子 | `rt:`(fanout), `seq:`(消息序号), `presence:`(在线), `dedup:`(幂等) | Pub/Sub 流量模式与 K/V 完全不同，必须独立 |

**Pub/Sub 必须独立 scene 的原因**：Redis Cluster 的 Pub/Sub 消息广播到所有节点，若混在 `general` 中会造成不必要的资源消耗和延迟抖动。

### 2.5 弹性扩展路径

| 用户规模 | rec | general | realtime | 上层代码改动 |
|---|---|---|---|---|
| < 10K (dev) | 三个 scene 共用 1 个 standalone（或 in-memory） | — | — | 零 |
| 10K ~ 50K | standalone | standalone | standalone | 零（改 config） |
| 50K ~ 500K | cluster | standalone | cluster | 零（改 config） |
| > 500K | cluster 独立扩缩 | cluster 独立扩缩 | cluster 独立扩缩 | 零（改 config） |

### 2.6 配置统一到 `runtime/config`

```yaml
redis:
  scenes:
    rec:
      mode: cluster              # standalone | cluster | memory
      addrs: [shard1:6379, shard2:6379, shard3:6379]
      password: ${REDIS_REC_PASSWORD}
      tls: true
      pool: { size: 0, min_idle: 0 }  # 0 = CPU-scaled auto
    general:
      mode: standalone
      addr: general-redis:6379
      password: ${REDIS_GENERAL_PASSWORD}
      db: 0
      pool: { size: 0 }
    realtime:
      mode: cluster
      addrs: [rt1:6379, rt2:6379, rt3:6379]
      password: ${REDIS_REALTIME_PASSWORD}
      tls: true
      pool: { size: 0 }

  prefix_routing:                # key prefix → scene 映射
    rec: [rec:]
    general: [cache:, page_ctx:, content_analysis:, comment_summary:,
              suggested_actions:, blocked_set:, device_tokens:,
              login_fail:, counter:, reaction:]
    realtime: [rt:, seq:, presence:, dedup:]
    fallback: general
```

### 2.7 服务接入方式（一行构建）

```go
func main() {
    cfg := config.MustLoad("configs/config.yaml")
    router := redis.MustNewRouter(cfg.Redis)
    defer router.Close()

    // Repository cache — general scene（metadata 声明的 cache_layer 自动生效）
    factory := repository.NewFactory(reg,
        repository.WithMongo(db),
        repository.WithCache(redis.NewCacheAdapter(router.Scene("general"))),
    )

    // 推荐热路径 — rec scene
    hotPath := rtrec.NewHotPath(redis.NewRecAdapter(router.Scene("rec")))

    // 页面上下文 — general scene
    pageCtx := rctx.NewPageContext(router.Scene("general"))

    // Chat seq/dedup — realtime scene
    seqGen := chat.NewSeqGenerator(router.Scene("realtime"))
    dedup := chat.NewDedupGuard(router.Scene("realtime"))

    // Pub/Sub fanout — realtime scene
    pubsub := router.Scene("realtime")
}
```

## 3. 向后兼容策略

### 3.1 现有接口适配

| 现有接口 | 适配方式 | 改动量 |
|---|---|---|
| `repository.CacheAdapter` | `redis.NewCacheAdapter(client Client) CacheAdapter` — 桥接 Get/Set/Del | 1 个 adapter，~30 行 |
| `recommendation.RedisClient` | `redis.NewRecAdapter(client Client) rtrec.RedisClient` — 桥接全部方法 | 1 个 adapter，~60 行 |
| `context.RedisClient` | 删除自定义接口，直接使用 `redis.Client`（方法签名兼容） | 修改 PageContext 构造函数 |

### 3.2 content-service 迁移

```
Before: main.go → buildRecRedisClient(cfg) → rtrec.NewHotPath(client)
After:  main.go → redis.MustNewRouter(cfg.Redis) → rtrec.NewHotPath(adapter)
```

同时 `repository.NewFactory` 加入 `WithCache`，metadata 声明的 Post/Circle 实体缓存**立即激活**。

### 3.3 redis-storage-elastic-infra 迁移

| 原节点 | 迁移目标 | 说明 |
|---|---|---|
| `redis-cluster-protocol` (L4) | `runtime-redis/unified-client-and-router/scene-pool-and-prefix-routing` | ClusterAdapter + hash tag 协议并入统一 Client |
| `redis-service-multicloud-config` (L4) | `runtime-redis/config-and-keyspace-contract/multi-scene-config-schema` | 多场景配置 schema 保留，扩展 realtime scene |
| `redis_keyspace.yaml` | 升级加入 `scene_routing` 段 + realtime 场景 key patterns | 保持唯一键空间文档地位 |

迁移后 `runtime-recommendation/redis-storage-elastic-infra` 标记 `archived=true`，引用指向 `runtime-redis`。

## 4. 功能范围

### 4.1 V1 交付（本次）

| 编号 | 功能 | 说明 |
|---|---|---|
| R1 | `redis.Client` 统一接口 | String + Hash + Set + Pub/Sub + Pipeline + Bytes |
| R2 | `redis.Router` scene 路由 | Scene() 显式路由 + ForKey() 前缀路由 |
| R3 | `ScenePool` 连接池管理 | standalone / cluster / memory 三种模式透明切换 |
| R4 | 适配桥接层 | NewCacheAdapter / NewRecAdapter / ctx 直接兼容 |
| R5 | 统一配置 schema | redis.scenes.{name} + prefix_routing 段 |
| R6 | redis_keyspace.yaml 升级 | 加入 realtime scene + scene_routing 段 |
| R7 | content-service 迁移 | 接入 Router + 激活 general cache |
| R8 | In-memory fallback | scene 无配置时自动降级为内存实现（本地开发） |
| R9 | 健康检查 | 每个 scene 暴露 ping + pool stats |
| R10 | 可观测性 | Prometheus 指标：连接数/命令延迟/错误率/per-scene |

### 4.2 V2 留待后续

- Redis Bloom Filter 适配（超大 exposed set 优化）
- 连接池动态调整（基于负载自动 scale pool size）
- Lua 脚本执行器（复杂原子操作）
- Redis Streams 适配（event sourcing 场景）

## 5. 约束

- 所有 Redis 操作必须通过 `runtime/redis.Router`，禁止服务层直接构建 `go-redis` 客户端
- 数据库驱动 `github.com/redis/go-redis/v9` 仅允许在 `runtime/redis` 和 `infrastructure/` 内 import
- key 必须以 `redis_keyspace.yaml` 中声明的 prefix 开头，未声明的 prefix → `make verify-metadata` 失败
- Pub/Sub channel 必须使用 `rt:` 前缀，路由到 realtime scene
- hash tag `{userId}` 约定保留（同用户 key 同 slot），扩展到 realtime scene 的 `seq:{conversationId}` 使用 `{conversationId}` hash tag
- 每个 scene 的 standalone/cluster 切换必须零代码改动，仅改 config
- In-memory fallback 仅用于 dev/test，prod 必须配置 Redis 地址（preflight 检查）

## 6. 验收标准（L2 总览）

| 编号 | 条件 | 验证层 |
|---|---|---|
| R-A1 | `redis.Client` 统一接口覆盖 String/Hash/Set/Pub-Sub/Pipeline/Bytes | L2 |
| R-A2 | `Router.Scene("rec"/"general"/"realtime")` 返回正确 scene Client | L2 |
| R-A3 | `Router.ForKey("cache:post:123")` 自动路由到 general scene | L2 |
| R-A4 | standalone ↔ cluster 切换仅改 config，测试通过 | L2 |
| R-A5 | NewCacheAdapter 桥接 Repository cache，FindByIDCached 走 Redis | L2 |
| R-A6 | NewRecAdapter 桥接 HotPath，rec scene 功能不退化 | L2 |
| R-A7 | Pub/Sub 在 realtime scene 跨两个 subscriber 正确路由 | L2 |
| R-A8 | Incr（seq 计数器）在 realtime scene 原子递增 | L2 |
| R-A9 | SetNX（dedup）在 realtime scene 幂等判断正确 | L2 |
| R-A10 | In-memory fallback：scene 无配置时自动降级，不报错 | L2 |
| R-A11 | Prometheus 指标 per-scene 可采集 | L2 |
| R-A12 | content-service 迁移后 rec + general 双 scene 正常工作 | L2 |
| R-A13 | make gate-full 通过（含 runtime-redis 契约测试） | L1~L2 |

## 7. 跨特性依赖

| 依赖 | 方向 | 说明 |
|---|---|---|
| runtime-repository | → | WithCache 接入 general scene |
| runtime-recommendation | → | HotPath 接入 rec scene |
| runtime-context | → | PageContext 接入 general scene |
| chat-conversation | → | seq/dedup/presence 接入 realtime scene |
| realtime-gateway | → | Pub/Sub fanout 接入 realtime scene |
| runtime-config | ← | 读取 redis.scenes 配置 |
| runtime-observability | ← | 指标 + 日志 + tracing |
| runtime-governance | ← | 连接池健康检查 + 熔断 |
