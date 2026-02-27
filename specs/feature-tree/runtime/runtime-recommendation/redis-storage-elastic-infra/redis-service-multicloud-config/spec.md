# L4 对象任务：redis-service-multicloud-config

## 功能说明

定义服务级 Redis **多场景配置 schema** 和**多云部署方案**，使 content-service（及未来所有服务）能够：

1. **场景分离**：`redis.rec`（推荐热路径）和 `redis.general`（实体缓存/安全限流/计数缓冲）独立配置、独立扩容；
2. **模式切换**：`mode: standalone`（本地/小规模）或 `mode: cluster`（生产）通过 1 个配置项切换；
3. **多云零代码切换**：阿里云 Tair 和火山引擎 VeCache 仅 env 变量不同；
4. **键空间契约**：`redis_keyspace.yaml` 补充 hash tag 约定和场景归属，作为跨服务统一文档。

## 已实现内容

| 交付物 | 文件 | 说明 |
|---|---|---|
| 多场景 config schema | `content-service/configs/config.yaml` | `redis.rec` + `redis.general` |
| config struct | `cmd/api/main.go: redisSceneCfg` | Go struct 对应 YAML 字段 |
| env 覆盖逻辑 | `cmd/api/main.go: applyEnvOverrides` | CONTENT_REDIS_REC_* 覆盖 |
| buildRecRedisClient | `cmd/api/main.go` | standalone/cluster 分支 + fallback |
| resolvePoolConfig | `cmd/api/main.go` | Pool 零值自动填充 CPU 基准 |
| 键空间文档 | `contracts/metadata/_shared/redis_keyspace.yaml` | hash tag + redis_scene 字段 |

## 适用范围与约束

**适用**：
- content-service（当前）
- 未来所有使用 Redis 的服务（参照 `redisSceneCfg` struct 复制或抽取到 runtime/config）

**不适用**：
- 本地开发（`addr` 留空 → in-memory fallback，无需任何 Redis 配置）

**约束**：
- `redis.rec.db` 字段在 `mode: cluster` 时被忽略（Redis Cluster 不支持 SELECT）
- `redis.general` 在 content-service 中当前未连接任何逻辑（预留）；其他服务使用时需在自身 main.go 中调用 `buildGeneralRedisClient`

## 验收标准

- A1：content-service 读取 `redis.rec.mode=cluster` + `addrs=[...]` 时创建 `RedisClusterAdapter`
- A2：`CONTENT_REDIS_REC_MODE=cluster` 环境变量覆盖 yaml 中 `mode: standalone`
- A3：旧 `CONTENT_REDIS_ADDR` 向后兼容，正确映射到 `redis.rec.addr`
- A4：`pool.size=0` 时自动使用 `DefaultClusterPoolConfig()` 或 `DefaultRedisPoolConfig()`
- A8：config 解析和 env 覆盖逻辑有单元测试
