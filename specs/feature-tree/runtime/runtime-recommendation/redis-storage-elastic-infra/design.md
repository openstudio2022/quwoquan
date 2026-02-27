# Design: redis-storage-elastic-infra

## 设计动因

随着 DAU 增长，单节点 Redis 遭遇两类瓶颈：

1. **内存上限**：单节点最大 ~512 GB，但单进程 GC 压力使实际可用上限约 100 GB；
2. **QPS 上限**：单节点约 10 万 QPS，推荐热路径写密集时会成为瓶颈。

Redis Cluster 通过分片解决内存和 QPS 两个问题，但引入了 **key 跨 slot 的约束**（pipeline / 事务要求同 slot）。因此，客户端适配和 key 设计必须提前解决。

## 为何此分解：L3 + 2×L4 而非平铺 L4

| 分解方案 | 优劣 |
|---|---|
| 直接在 `redis-hot-path-and-rule-engine` 追加任务 | ❌ 混淆算法层和基础设施层职责；未来 general-cache 场景无处挂载 |
| 新建 L2 `runtime-storage-elastic` | ❌ 过重；当前仅 Redis，MongoDB/向量存储弹性尚无计划 |
| 新建 L3 `redis-storage-elastic-infra` 挂在 `runtime-recommendation` | ✅ runtime 层与算法层平级；可扩展（未来挂 general-cache 等 L4）；不破坏既有树结构 |
| 挂在 `platform-ops-governance` | ❌ 该 L1 聚焦治理策略，不是代码实现；ClusterAdapter 是 Go 代码，不是策略 |

## 业界对标

| 项目 | 做法 |
|---|---|
| TikTok 推荐 | Redis Cluster（64 分片）用于实时特征，hash tag `{userId}` 确保 session key 同 slot |
| 微信 / 朋友圈 | 分场景 Redis（时间线热路径 vs 点赞计数），独立扩容 |
| 阿里云 Tair | 标准 Redis Cluster API + 在线扩容（无停机） |
| 火山引擎 VeCache | 标准 Redis Cluster API + 弹性 API 自动扩容 |

**关键洞察**：两大云厂商均遵循 Redis Cluster 协议，客户端代码无需区分厂商，仅连接地址/密码/TLS 不同 → **env 变量注入，代码零差异**。

## 多方案对比：hash tag 策略

| 方案 | 说明 | 评估 |
|---|---|---|
| **A：`{userId}` hash tag（本方案）** | `{user123}:sessionId` | ✅ 同用户所有 session key 同 slot；pipeline 高效；standalone 透明 |
| B：`{userId}:{sessionId}` hash tag | hash tag 包含 sessionId | ❌ 不同 session 可能不同 slot，无法跨 session pipeline |
| C：不用 hash tag | key 随机分布 | ❌ pipeline 在 cluster 模式退化为多 RTT；GetSessionState 性能损失 3× |
| D：仅用 userId 做 key（无 sessionId） | 牺牲多 session 隔离 | ❌ 不符合 session 级别信号隔离需求 |

**选择方案 A**：`{userId}` hash tag 是覆盖范围最小、安全性最高的选择（仅锁定同用户，不锁定同 session）。

## 适用场景与约束

**适用**：
- 所有使用 `HotPath` / `SessionCache` / `BufferedHotPath` 的服务
- 阿里云 Tair 集群版 / 火山引擎 VeCache 集群版 / 自建 Redis Cluster

**约束与局限**：
- Cluster 模式下不能使用 `SELECT <db>` 命令；`db` 配置项仅 standalone 模式有效
- `{userId}` hash tag 使同一用户的所有 session key 集中在一个 slot → hot slot 风险（极端情况：某用户请求量极大时单 shard 过热）；规避方式：限流 + 排队（在 governance 层处理）
- PipelineRead 中所有 op 的 key 必须共享相同 hash tag；调用方（HotPath）负责保证此约束

## 当前态 → 目标态

| 维度 | 当前态（改动前） | 目标态（本特性完成后） |
|---|---|---|
| Redis 客户端 | 仅 standalone `redis.Client` | standalone + cluster `redis.ClusterClient` |
| key 格式 | `userId:sessionId`（无 hash tag） | `{userId}:sessionId`（cluster-safe） |
| 配置 | 单个 `redis.addr` 字段 | `redis.rec` + `redis.general` 双场景，各含 mode/addrs/tls |
| 多云支持 | 无 | 阿里云 Tair + 火山引擎 VeCache，env 注入切换 |
| in-memory fallback | 保留 | 保留（本地开发） |

## 未来演进

1. **general-cache 场景上线**：当实体缓存、计数缓冲在 content-service 或 user-service 实现后，`redis-service-multicloud-config` 下新增对应 L4/L5 节点，使用 `redis.general` 配置分支。
2. **Bloom Filter 优化 exposed_set**：超大 session（> 10 万曝光 ID）时改用 Redis Bloom Filter（`RedisBloomAdapter`），在 L4a 的后续演进任务中跟踪。
3. **热点 slot 监控**：接入 CloudWatch (Tair) / 监控大盘 (VeCache) 告警，纳入 `observability-and-alerting` 节点。
