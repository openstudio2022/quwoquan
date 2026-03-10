# L4 对象任务：redis-cluster-protocol

## 功能说明

在 `runtime/recommendation` 层实现 Redis Cluster 所需的两项底层能力：

1. **`{userId}` hash tag 协议**：修改 `HotPath.sessionKey()` 使同一用户的所有 session 相关 key（`rec:session_signals`、`rec:exposed`、`rec:negative`、`rec:realtime_interest`）共享相同 hash tag → 保证同 slot → pipeline 合法。

2. **`RedisClusterAdapter`**：新的 `rtrec.RedisClient` + `rtrec.RedisPipeliner` 实现，封装 `redis.ClusterClient`，支持 TLS（阿里云/火山引擎公网端点必需）、副本延迟路由（`RouteByLatency`）、以及更高的连接池基准（CPU×30）。

## 已实现接口归属

| 接口 | 实现 | 文件 |
|------|------|------|
| `RedisClient` | `RedisClusterAdapter` | `infrastructure/recommendation/redis_client.go` |
| `RedisPipeliner` | `RedisClusterAdapter.PipelineRead` | 同上 |
| `RedisClient` | `RedisClientAdapter`（standalone，原有） | 同上 |
| hash tag sessionKey | `HotPath.sessionKey()` | `runtime/recommendation/hotpath.go` |

## 适用范围与约束

**适用**：所有使用 `HotPath` / `SessionCache` / `BufferedHotPath` 的服务。

**约束**：
- `PipelineRead` 调用方必须保证同批次所有 key 共享相同 hash tag（HotPath 负责保证，其他调用方须遵守）
- `RedisClusterAdapter` 不支持 `SELECT <db>` 命令（Redis Cluster 协议限制）
- standalone 模式下 hash tag `{userId}` 被 Redis 透明忽略，key 内容含花括号但功能不变

## 验收标准

- A1：`sessionKey("u1","s1")` 返回 `"{u1}:s1"`
- A2：`RedisClusterAdapter` 通过 `RedisClient` 接口的所有方法测试
- A3：`RedisClusterAdapter.PipelineRead` 执行 3 op（HGetAll + SMembers + SMembers），在 cluster 模式下仅发送 1 次网络请求
- A8：单元测试覆盖 hash tag 格式；接口测试覆盖 ClusterAdapter 所有方法
