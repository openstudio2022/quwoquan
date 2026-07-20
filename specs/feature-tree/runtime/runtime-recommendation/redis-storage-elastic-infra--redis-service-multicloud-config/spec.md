# L3 对象任务：redis-service-multicloud-config

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
| env 覆盖逻辑 | `cmd/api/runtime_config_and_projection.go: applyEnvOverrides` | 仅接受具名 scene 的 `CONTENT_REDIS_REC_* / GENERAL_* / REALTIME_*` |
| Redis router | `cmd/api/main.go` | production composition 显式装配 standalone/cluster adapter；缺 scene 配置时启动失败 |
| 运行时预检 | `cmd/api/runtime_config_and_projection.go: preflightConfig` | 禁止 memory mode、空地址与旧单 scene env 回退 |
| 键空间文档 | `contracts/metadata/_shared/redis_keyspace.yaml` | hash tag + redis_scene 字段 |

## 适用范围与约束

**适用**：
- content-service（当前）
- 未来所有使用 Redis 的服务（参照 `redisSceneCfg` struct 复制或抽取到 runtime/config）

**不适用**：
- 纯函数单元测试；真实服务进程在 alpha/beta/gamma/prod 均须由环境清单提供 Redis，禁止进程内 fallback

**约束**：
- `redis.rec.db` 字段在 `mode: cluster` 时被忽略（Redis Cluster 不支持 SELECT）
- `redis.rec/general/realtime` 均为显式 scene；任何 scene 依赖缺失均由启动预检阻断
- 旧 `CONTENT_REDIS_ADDR / CONTENT_REDIS_PASSWORD / CONTENT_REDIS_DB` 已退役且不会被读取

## 验收标准

- A1：content-service 读取 `redis.rec.mode=cluster` + `addrs=[...]` 时创建 `RedisClusterAdapter`
- A2：`CONTENT_REDIS_REC_MODE=cluster` 环境变量覆盖 yaml 中 `mode: standalone`
- A3：旧单 scene Redis 环境变量不产生任何配置效果；仅具名 scene 变量可覆盖 YAML
- A4：`pool.size=0` 时自动使用 `DefaultClusterPoolConfig()` 或 `DefaultRedisPoolConfig()`
- A8：config 解析和 env 覆盖逻辑有单元测试
