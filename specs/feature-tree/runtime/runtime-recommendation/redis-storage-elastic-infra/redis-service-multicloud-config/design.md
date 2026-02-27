# Design: redis-service-multicloud-config

## 设计动因

原 config 仅有 `redis.addr/password/db` 三个字段（单节点 standalone），无法表达：
- 多场景（rec / general）独立扩容的需求
- cluster 模式的多节点地址（addrs）
- TLS（阿里云/火山引擎公网端点必须）
- 场景级 pool 调优（rec 追求低延迟，general 追求吞吐）

## 多方案对比

| 方案 | 说明 | 评估 |
|---|---|---|
| **A：多场景嵌套 YAML（本方案）** | `redis.rec` + `redis.general` 各一套 config | ✅ 独立扩容；各自 pool 调优；按场景描述意图 |
| B：单一 Redis + 分 DB（db 0/1） | 原方案 + `redis.db_rec=0, db_general=1` | ❌ cluster 不支持 SELECT；db 隔离弱于实例隔离 |
| C：服务级 Redis（每服务独立实例，单一配置） | content-service 只有一个 redis 实例 | ❌ 未来 general cache 和 rec 共享同实例，无法独立扩容 |
| D：在 runtime/config 提取公共 RedisConfig struct | 让所有服务共享配置结构 | 🔶 更优（长期目标），但当前仅一个服务，过早抽象，搁置 |

## 多云兼容性：无代码差异

| 云厂商 | 端点类型 | 推荐 env 配置 |
|---|---|---|
| 阿里云 Tair 集群版（内网） | `r-xxx.redis.rds.aliyuncs.com:6379` 等多节点 | `MODE=cluster, ADDRS=n1:6379,n2:6379,..., TLS=false` |
| 阿里云 Tair 集群版（公网/加密） | `r-xxx.redis.rds.aliyuncs.com:6380` | `MODE=cluster, ADDRS=..., TLS=true` |
| 火山引擎 VeCache 集群版（内网） | `cache-cn-xxx.vecache.volces.com:6379` 等 | `MODE=cluster, ADDRS=n1:6379,..., TLS=false` |
| 火山引擎 VeCache 集群版（公网） | 同上 + 6380 端口 | `MODE=cluster, ADDRS=..., TLS=true` |
| 自建 Redis Cluster | 任意 | `MODE=cluster, ADDRS=...` |
| 本地开发 | Docker Redis single node | `MODE=standalone, ADDR=localhost:6379` |
| 单元测试 | in-memory | 不设置任何 ADDR（fallback） |

## env 变量覆盖优先级链

```
env var  >  config.yaml  >  代码默认值（空字符串 / 0 / false）
```

向后兼容：
- `CONTENT_REDIS_ADDR` → `redis.rec.addr`（standalone）
- `CONTENT_REDIS_PASSWORD` → `redis.rec.password`
- `CONTENT_REDIS_DB` → `redis.rec.db`

## Pool 配置零值策略

```
pool.size == 0  →  standalone: CPU×20 / cluster: CPU×30
pool.min_idle == 0  →  standalone: CPU×5 / cluster: CPU×8
pool.*_timeout_ms == 0  →  rec: 100ms / general: 200ms（由 DefaultXxxPoolConfig() 提供）
```

显式配置始终优先于默认值，允许生产环境精确调优。

## 适用场景与约束

**适用**：content-service 及任何需要 Redis 的新服务（通过复制 `redisSceneCfg` struct 模式）。

**局限**：
- `redisSceneCfg` 目前在 `cmd/api/main.go` 内定义，未提取到 runtime；多个服务时需复制（技术债）
- 触发提取时机：≥ 2 个服务需要相同配置结构时，提取到 `quwoquan_service/runtime/config`

## 未来演进

- [ ] 将 `redisSceneCfg` 提取到 `quwoquan_service/runtime/config`，供所有服务共享（触发条件：第 2 个服务需要 Redis）
- [ ] general 场景接线（content-service 实体缓存 / 计数缓冲启动时激活）
- [ ] 配置中心支持（K8s ConfigMap / 阿里云 ACM / 火山引擎 Config）——将 env 变量来源从 Pod 环境变量迁移到配置中心
