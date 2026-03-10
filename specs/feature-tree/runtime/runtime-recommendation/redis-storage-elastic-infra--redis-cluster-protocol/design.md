# Design: redis-cluster-protocol

## 设计动因

原 `sessionKey()` 返回 `userId:sessionId`（无 hash tag），在 Redis Cluster 模式下：
- `rec:session_signals:u1:s1`、`rec:exposed:u1:s1`、`rec:negative:u1:s1` 三个 key 因 CRC16 分布，有 ~97% 概率落在不同 slot；
- `PipelineRead` 在 cluster 模式下必须对每个 slot 单独发一次 pipeline → 退化为 3 RTT，抵消 pipeline 优化效果。

## 方案决策：{userId} hash tag 覆盖所有 session key

`sessionKey()` 改为返回 `{userId}:sessionId`：

```
rec:session_signals:{u1}:s1   → hash = CRC16("u1") % 16384 = slot X
rec:exposed:{u1}:s1          → hash = CRC16("u1") % 16384 = slot X  ✓ 同 slot
rec:negative:{u1}:s1         → hash = CRC16("u1") % 16384 = slot X  ✓ 同 slot
```

**优点**：
- 单次 pipeline 1 RTT（原 3 RTT / 3 goroutine 并行）
- standalone 模式透明兼容（Redis 忽略花括号，key 等价于无 tag）
- 不影响 HotPath 外部调用接口（`GetSessionState(userID, sessionID)` 签名不变）

**权衡（hot slot 风险）**：
- 同用户所有 session 的写都打到同一 shard
- 缓解措施：`BufferedHotPath` 已有异步写入缓冲（50ms / 64 条批写），峰值已被平滑；L1 `SessionCache` 减少读穿透
- 极端场景（同一用户请求量异常大）由上层限流处理，不在本节点范围内

## RedisClusterAdapter 设计

基于 `github.com/redis/go-redis/v9` 的 `redis.ClusterClient`，与 `RedisClientAdapter`（standalone）共享相同的 `RedisClient` + `RedisPipeliner` 接口。

| 差异项 | standalone RedisClientAdapter | cluster RedisClusterAdapter |
|---|---|---|
| 底层客户端 | `redis.Client` | `redis.ClusterClient` |
| DB 选择 | 支持（`SELECT <db>`） | 不支持（cluster 不允许 SELECT） |
| 默认 PoolSize | CPU×20 | CPU×30（连接分布到多个 shard） |
| 默认 MinIdleConns | CPU×5 | CPU×8 |
| TLS | 不默认开启 | 可选（`tls.VersionTLS12`） |
| RouteByLatency | 不适用 | `true`（读请求路由到延迟最低副本） |

## 适用场景与约束

**适用**：DAU > 5 万或推荐热路径 Redis > 8 GB。

**约束**：
- `PipelineRead` 同批次 key 必须共享相同 hash tag（调用方职责）
- cluster 模式不支持 `MULTI/EXEC` 跨 slot 事务
- `db` 配置项在 cluster 模式下被忽略（无需报错，config 层已有文档说明）

## 未来演进

- [ ] **Bloom Filter 支持**：超大 exposed_set（> 10 万 ID）改用 `RedisBloomAdapter`，实现 `SAddWithBloom` / `SIsMemberBloom`；需引入 `go-redis/v9` 的 Bloom Filter 命令扩展
- [ ] **读写分离 replica 路由**：已有 `RouteByLatency`；未来可按场景定制路由策略（session 读 → replica，session 写 → primary）
